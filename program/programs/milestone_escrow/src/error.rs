use anchor_lang::prelude::*;

#[error_code]
pub enum EscrowError {
    #[msg("Amount must be greater than zero")]
    ZeroAmount,
    #[msg("Deadline must be in the future")]
    DeadlineInPast,
    #[msg("Signer is not the oracle stored in the milestone")]
    WrongOracle,
    #[msg("Payment can only go to the contractor stored in the milestone")]
    WrongContractor,
    #[msg("Signer is not the investor stored in the milestone")]
    WrongInvestor,
    #[msg("Milestone is not open: it was already approved, released or refunded")]
    NotOpen,
    #[msg("Deadline has passed, approval is no longer possible")]
    DeadlinePassed,
    #[msg("Deadline has not passed yet, refund is not possible")]
    DeadlineNotReached,
    #[msg("QA was run against a different ruleset than the one frozen in the milestone")]
    RulesetMismatch,
    // Appended last so existing error numbers (6000–6008) do not shift.
    #[msg("Amount is below the rent-exempt minimum: payment to an empty wallet could never succeed")]
    AmountBelowRentMinimum,
    // Dispute window (P1). Appended last: 6000–6009 above keep their numbers.
    #[msg("Dispute window must be between 10 seconds and 7 days")]
    InvalidDisputeWindow,
    #[msg("Arbiter must be someone other than the investor, the contractor and the oracle")]
    ArbiterNotIndependent,
    #[msg("Milestone is not approved (or disputed): nothing to dispute or claim")]
    NotApproved,
    #[msg("Dispute window has closed")]
    DisputeWindowClosed,
    #[msg("Signer is not the arbiter stored in the milestone")]
    WrongArbiter,
    #[msg("Milestone is not disputed: nothing for the arbiter to decide")]
    NotDisputed,
    #[msg("The arbiter's time to decide is over: the oracle's approval stands")]
    ArbiterPeriodOver,
    #[msg("Payment is not claimable yet: the dispute window is still open")]
    ClaimTooEarly,
}
