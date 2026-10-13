use anchor_lang::prelude::*;

/// One payment for one deliverable. The account itself holds the locked lamports
/// (on top of its rent-exempt reserve) and stays on chain as a permanent record.
#[account]
#[derive(InitSpace)]
pub struct Milestone {
    pub investor: Pubkey,
    pub contractor: Pubkey,
    pub oracle: Pubkey,
    /// Decides a dispute: pay the contractor or refund the investor. Nothing else.
    pub arbiter: Pubkey,
    /// Lamports locked for the contractor.
    pub amount: u64,
    /// SHA-256 of the acceptance rules (IDS file). Frozen at creation.
    pub ruleset_hash: [u8; 32],
    /// Unix timestamp. Approval allowed up to it, refund of an open milestone only after it.
    pub deadline: i64,
    /// Seconds the investor has to dispute an approval, and the arbiter has to decide a dispute.
    pub dispute_window: i64,
    pub status: Status,
    /// Unix timestamp of the oracle's approval, 0 until then.
    pub approved_at: i64,
    /// Unix timestamp of the investor's dispute, 0 until then.
    pub disputed_at: i64,
    /// SHA-256 of the accepted IFC file, set on approval.
    pub asset_hash: [u8; 32],
    /// SHA-256 of the accepted QA result, set on approval.
    pub result_hash: [u8; 32],
    pub milestone_id: u64,
    pub bump: u8,
}

#[derive(AnchorSerialize, AnchorDeserialize, Clone, Copy, PartialEq, Eq, InitSpace, Debug)]
pub enum Status {
    Open,
    Approved,
    Disputed,
    Released,
    Refunded,
}
