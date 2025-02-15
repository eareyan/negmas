"""Opponent modeling base classes

"""
import random
from abc import ABC, abstractmethod
from typing import Union, Collection, List, TYPE_CHECKING

import numpy as np

from negmas.outcomes import Outcome, ResponseType
from negmas.common import *

if TYPE_CHECKING:
    from negmas.sao import SAONegotiator

__all__ = ['AcceptanceModel', 'AdaptiveAcceptanceModel', 'RandomAcceptanceModel', 'PeekingAcceptanceModel'
    , 'AggregatingAcceptanceModel', 'UncertainOpponentModel', 'PeekingProbabilisticAcceptanceModel']


class AcceptanceModel(ABC):
    """"""
    def __init__(self, outcomes: Collection[Outcome]):
        outcomes = list(outcomes)
        self.outcomes = outcomes
        self.indx = dict(zip(outcomes, range(len(outcomes))))

    def probability_of_acceptance(self, outcome: 'Outcome'):
        indx = self.indx.get(outcome, None)
        if indx is None:
            return 0.0
        return self.probability_of_acceptance_indx(indx)

    def update_rejected(self, outcome: 'Outcome'):
        if outcome is None:
            return
        return self.update_rejected_indx(self.indx[outcome])

    def update_offered(self, outcome):
        if outcome is None:
            return
        return self.update_offered_indx(self.indx[outcome])

    def update_accepted(self, outcome):
        return self.update_offered(outcome=outcome)

    def acceptance_probabilities(self) -> np.ndarray:
        return np.array([self.probability_of_acceptance_indx(_) for _ in range(len(self.outcomes))])

    @abstractmethod
    def probability_of_acceptance_indx(self, outcome_index: int) -> float:
        raise NotImplementedError()

    @abstractmethod
    def update_rejected_indx(self, outcome_index: int):
        raise NotImplementedError()

    @abstractmethod
    def update_offered_indx(self, outcome_index: int):
        raise NotImplementedError()


class AdaptiveAcceptanceModel(AcceptanceModel):
    def __init__(self, outcomes: Collection[Outcome]
                 , n_negotiators: int = 2
                 , prob: Union[float, List[float]] = 0.5
                 , end_prob=0.0
                 , p_accept_after_reject=0.0
                 , p_reject_after_accept=0.0
                 , rejection_discount=0.98
                 , rejection_delta=0.0
                 , not_offering_rejection_ratio=0.75
                 ):
        super().__init__(outcomes=outcomes)
        outcomes = self.outcomes
        if isinstance(prob, list) and len(outcomes) != len(prob):
            raise ValueError(f'{len(outcomes)} outcomes but {len(prob)} probabilities. Cannot initialize simple '
                             f'opponents model')
        self.n_agents = n_negotiators
        if not isinstance(prob, Collection):
            self.p = np.array([prob for _ in range(len(outcomes))])
        else:
            self.p = np.array(list(prob))
        self.end_prob = end_prob
        self.p_accept_after_reject = p_accept_after_reject
        self.p_accept_after_accept = 1 - p_reject_after_accept
        self.delta = rejection_delta
        self.discount = rejection_discount
        self.first = True
        self.not_offered = set(list(range(len(self.outcomes))))
        self.not_offering_rejection_ratio = not_offering_rejection_ratio
        self.not_offering_discount = self.discount + (1.0 - self.not_offering_rejection_ratio) * (1.0-self.discount)

    @classmethod
    def from_negotiation(cls, info: MechanismInfo
                         , prob: Union[float, list] = 0.5
                         , end_prob=0.0
                         , p_accept_after_reject=0.0
                         , p_reject_after_accept=0.0) -> 'AdaptiveAcceptanceModel':
        if not info.n_outcomes or info.outcomes is None:
            raise ValueError('Cannot initialize this simple opponents model for a negotiation with uncountable outcomes')
        return cls(outcomes=info.outcomes, n_negotiators=info.n_negotiators
                   , prob=prob, end_prob=end_prob, p_accept_after_reject=p_accept_after_reject
                   , p_reject_after_accept=p_reject_after_accept)

    def probability_of_acceptance_indx(self, outcome_index: int) -> float:
        return self.p[outcome_index]

    def acceptance_probabilities(self):
        """Probability of acceptance for all outcomes"""
        return self.p

    def _update(self, p: float, real_rejection: bool) -> float:
        if real_rejection:
            return min(self.p_accept_after_reject, min(1.0,  (p - self.delta) * self.discount))
        else:
            return max(self.p_accept_after_reject, min(1.0, (p - self.delta*self.not_offering_rejection_ratio) * self.not_offering_discount))

    def update_rejected_indx(self, outcome_index: int):
        self.p[outcome_index] = self._update(self.p[outcome_index], real_rejection=True)

    def update_offered_indx(self, outcome_index: int):
        try:
            self.not_offered.remove(outcome_index)
            self.p[outcome_index] = self.p_accept_after_accept
            # for i in self.not_offered:
            #    self.p[i] = self._update(self.p[i], real_rejection=False)
        except KeyError:
            pass


class RandomAcceptanceModel(AcceptanceModel):
    def __init__(self, outcomes: Collection[Outcome], **kwargs):
        super().__init__(outcomes=outcomes)

    def probability_of_acceptance_indx(self, outcome_index: int) -> float:
        return random.random()

    def update_rejected_indx(self, outcome_index: int):
        pass

    def update_offered_indx(self, outcome_index: int):
        pass


class ConstantAcceptanceModel(AcceptanceModel):
    def __init__(self, outcomes: Collection[Outcome], **kwargs):
        super().__init__(outcomes=outcomes)

    def probability_of_acceptance_indx(self, outcome_index: int) -> float:
        return 0.5

    def update_rejected_indx(self, outcome_index: int):
        pass

    def update_offered_indx(self, outcome_index: int):
        pass


class PeekingAcceptanceModel(AcceptanceModel):
    def __init__(self, outcomes: Collection[Outcome], opponents: Union['SAONegotiator', Collection['SAONegotiator']]):
        super().__init__(outcomes=outcomes)
        if not isinstance(opponents, Collection):
            opponents = [opponents]
        self.opponents = opponents

    def probability_of_acceptance_indx(self, outcome_index: int) -> float:
        outcome = self.outcomes[outcome_index]
        for opponent in self.opponents:
            if opponent is self:
                continue
            if opponent.mechanism_info is None:
                response = ResponseType.REJECT_OFFER
            else:
                response = opponent.respond_(state=opponent.mechanism_info.state, offer=outcome)
            if response != ResponseType.ACCEPT_OFFER:
                return 0.0
        return 1.0

    def update_rejected_indx(self, outcome_index: int):
        pass

    def update_offered_indx(self, outcome_index: int):
        pass


class PeekingProbabilisticAcceptanceModel(AcceptanceModel):
    def __init__(self, outcomes: Collection[Outcome], opponents: Union['SAONegotiator', Collection['SAONegotiator']]):
        super().__init__(outcomes=outcomes)
        if not isinstance(opponents, Collection):
            opponents = [opponents]
        self.opponents = opponents

    def probability_of_acceptance_indx(self, outcome_index: int) -> float:
        outcome = self.outcomes[outcome_index]
        if outcome is None:
            return 0.0
        prod = 1.0
        for o in self.opponents:
            prod *= o.ufun(outcome) # type: ignore
        return prod

    def update_rejected_indx(self, outcome_index: int):
        pass

    def update_offered_indx(self, outcome_index: int):
        pass


class AggregatingAcceptanceModel(AcceptanceModel):
    def __init__(self, outcomes: Collection[Outcome], models: List[AcceptanceModel], weights: List[float] = None):
        super().__init__(outcomes=outcomes)
        if weights is None:
            weights = [1.0] * len(self.outcomes)
        s = sum(weights)
        weights = [_ / s for _ in weights]
        self.models = models
        self.weights = weights

    def probability_of_acceptance_indx(self, outcome_index: int) -> float:
        p = 0.0
        for model, w in zip(self.models, self.weights):
            p += w * model.probability_of_acceptance_indx(outcome_index=outcome_index)
        return min(1.0, max(0.0, p))

    def update_rejected_indx(self, outcome_index: int):
        for model in self.models:
            model.update_rejected_indx(outcome_index=outcome_index)

    def update_offered_indx(self, outcome_index: int):
        for model in self.models:
            model.update_offered_indx(outcome_index=outcome_index)


class UncertainOpponentModel(AggregatingAcceptanceModel):
    """A model for which the uncertainty about the acceptance probability of different negotiators is controllable.

    This is not a realistic model but it can be used to experiment with effects of this uncertainty on different
    negotiation related algorithms (e.g. elicitation algorithms)

    Args:
        outcomes: The list of possible outcomes
        uncertainty (float): The uncertainty level. Zero means no uncertainty and 1.0 means maximum uncertainty
        adaptive (bool): If true then the random part will learn from experience with the opponents otherwise it will not.
        rejection_discount: Only effective if adaptive is True. See `AdaptiveAcceptanceModel`
        rejection_delta: Only effective if adaptive is True. See `AdaptiveAcceptanceModel`

    """
    def __init__(self, outcomes: Collection[Outcome]
                 , opponents: Union['SAONegotiator', Collection['SAONegotiator']]
                 , uncertainty: float = 0.5
                 , adaptive: bool = False
                 , rejection_discount: float = 0.95
                 , rejection_delta: float = 0.0
                 , constant_base=True
                 , accesses_real_acceptance=False
                 ):
        randomizing_model: AcceptanceModel
        peaking_model: AcceptanceModel
        if adaptive:
            randomizing_model = AdaptiveAcceptanceModel(outcomes=outcomes
                                                        , rejection_discount=rejection_discount
                                                        , rejection_delta=rejection_delta)
        elif constant_base:
            randomizing_model = ConstantAcceptanceModel(outcomes=outcomes)
        else:
            randomizing_model = RandomAcceptanceModel(outcomes=outcomes)
        if accesses_real_acceptance:
            peaking_model = PeekingAcceptanceModel(opponents=opponents, outcomes=outcomes)
        else:
            peaking_model = PeekingProbabilisticAcceptanceModel(opponents=opponents, outcomes=outcomes)
        if uncertainty < 1e-7:
            super().__init__(outcomes=outcomes,models=[peaking_model], weights=[1.0])
        elif uncertainty > 1.0-1e-7:
            super().__init__(outcomes=outcomes,models=[randomizing_model], weights=[1.0])
        else:
            super().__init__(outcomes=outcomes, models=[peaking_model, randomizing_model]
                             , weights=[1.0 - uncertainty, uncertainty])
