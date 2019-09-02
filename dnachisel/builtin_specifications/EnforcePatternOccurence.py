"""Implement AvoidPattern"""

from ..Specification import Specification


# from .VoidSpecification import VoidSpecification
from ..SpecEvaluation import SpecEvaluation
from .EnforceSequence import EnforceSequence
from ..MutationSpace import MutationSpace
from ..SequencePattern import SequencePattern, DnaNotationPattern
from ..Location import Location
from ..biotools import reverse_complement
from ..DnaOptimizationProblem import DnaOptimizationProblem, NoSolutionError


class EnforcePatternOccurence(Specification):
    """Enforce a number of occurences of the given pattern in the sequence.

    Parameters
    ----------
    pattern
      A SequencePattern or DnaNotationPattern

    enzyme
      Enzyme name, can be provided instead of a pattern

    occurences
      Desired number of occurences of the pattern.

    location
      Location of the DNA segment on which to enforce the pattern e.g.
      ``Location(10, 45, 1)``

    center
      If true, new inserted patterns will prioritize locations at the center
      of the specification's location. Else the insertion will happen at
      the beginning of the location.
    """

    best_possible_score = 0
    priority = -1
    genbank_args = ("pattern", "occurences")

    def __init__(
        self, pattern=None, occurences=1, location=None, center=True, boost=1.0
    ):
        """Initialize."""
        if isinstance(pattern, str):
            pattern = SequencePattern.from_string(pattern)
        self.pattern = pattern
        if isinstance(location, tuple):
            location = Location.from_tuple(location)
        self.location = location
        self.boost = boost
        self.occurences = occurences
        self.center = center
        self.boost = boost

    def initialize_on_problem(self, problem, role=None):
        return self._copy_with_full_span_if_no_location(problem)
        # if self.location is None:
        #     location = Location(0, len(problem.sequence))
        #     return self.copy_with_changes(location=location)
        # else:
        #     return self

    def evaluate(self, problem):
        """Score the difference between expected and observed n_occurences."""
        matches = self.pattern.find_matches(problem.sequence, self.location)
        score = -abs(len(matches) - self.occurences)

        if score == 0:
            message = "Passed. Pattern found at positions %s" % matches
        else:
            if self.occurences == 0:
                message = "Failed. Pattern not found."
            else:
                message = (
                    "Failed. Pattern found %d times instead of %d"
                    " wanted, at locations %s"
                ) % (len(matches), self.occurences, matches)
        return SpecEvaluation(
            self,
            problem,
            score,
            message=message,
            locations=[self.location],
            data=dict(matches=matches),
        )

    def localized(self, location, problem=None):
        """Localize the evaluation."""
        new_location = self.location.overlap_region(location)
        if new_location is None:
            return None
        # VoidSpecification(parent_specification=self)
        else:
            return self

    def insert_pattern_in_problem(self, problem, reverse=False):
        """Insert the pattern in the problem's sequence by successive tries.

        This heuristic is attempted to get the number of occurences in the
        pattern from 0 to some number
        """
        sequence_to_insert = self.pattern.sequence
        if reverse:
            sequence_to_insert = reverse_complement(sequence_to_insert)
        L = self.pattern.size
        starts = range(self.location.start, self.location.end - L)
        if self.center:
            center = 0.5 * (self.location.start + self.location.end)
            starts = sorted(starts, key=lambda s: abs(s - center))
        for start in starts:
            new_location = Location(start, start + L, self.location.strand)
            new_constraint = EnforceSequence(
                sequence=sequence_to_insert, location=new_location
            )
            new_space = MutationSpace.from_optimization_problem(
                problem, new_constraints=[new_constraint]
            )
            if len(new_space.unsolvable_segments) > 0:
                continue
            new_sequence = new_space.constrain_sequence(problem.sequence)
            new_constraints = problem.constraints + [new_constraint]
            new_problem = DnaOptimizationProblem(
                sequence=new_sequence,
                constraints=new_constraints,
                mutation_space=new_space,
                logger=None,
            )
            if self.evaluate(new_problem).passes:
                try:
                    new_problem.resolve_constraints()
                    problem.sequence = new_problem.sequence
                    return
                except NoSolutionError:
                    pass
        if (not reverse) and (self.pattern.in_both_strands):
            self.insert_pattern_in_problem(problem, reverse=True)
            return
        raise NoSolutionError(
            problem=problem,
            location=self.location,
            message="Insertion of pattern %s in %s failed"
            % (self.pattern.sequence, self.location),
        )

    def resolution_heuristic(self, problem):
        """Resolve using custom instertion if possible."""
        if isinstance(self.pattern, DnaNotationPattern):
            evaluation = self.evaluate(problem)
            if evaluation.passes:
                return
            n_matches = len(evaluation.data["matches"])
            if n_matches < self.occurences:
                other_constraints = [
                    c for c in problem.constraints if c is not self
                ]
                new_problem = problem
                for i in range(self.occurences - n_matches):
                    new_occurence_cst = self.copy_with_changes(
                        occurences=n_matches + i + 1
                    )
                    new_problem = DnaOptimizationProblem(
                        sequence=new_problem.sequence,
                        constraints=other_constraints + [new_occurence_cst],
                        mutation_space=problem.mutation_space
                    )
                    new_occurence_cst.insert_pattern_in_problem(new_problem)
                problem.sequence = new_problem.sequence
                return
        problem.resolve_constraints_locally()  # default resolution method

    def label_parameters(self):
        # result = [('enzyme', self.enzyme) if (self.enzyme is not None)
        #           else (self.pattern.sequence
        #                 if hasattr(self.pattern, 'sequence')
        #                 else str(self.pattern))]
        result = [str(self.pattern)]
        if self.occurences != 1:
            result += ["occurence", str(self.occurences)]
        return result
