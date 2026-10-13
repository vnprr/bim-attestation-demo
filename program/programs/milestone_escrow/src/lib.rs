use anchor_lang::prelude::*;
use anchor_lang::system_program;

pub mod error;
pub mod state;

pub use error::EscrowError;
pub use state::{Milestone, Status};

declare_id!("8v9W8niNQCq5VDvh9nuv24Er7bVFqHcbWp4dboGNKSTo");

#[constant]
pub const MILESTONE_SEED: &[u8] = b"milestone";
pub const MIN_DISPUTE_WINDOW: i64 = 10;
pub const MAX_DISPUTE_WINDOW: i64 = 7 * 24 * 60 * 60;

/// Six instructions. Money moves only in `claim`, `resolve` and `refund`: each needs a specific
/// non-final status and sets a final one, so a milestone pays out at most once. There is
/// deliberately no instruction that changes `ruleset_hash`, `oracle`, `contractor`, `arbiter`
/// or `dispute_window` after creation.
#[program]
pub mod milestone_escrow {
    use super::*;

    /// Investor locks `amount` lamports and freezes the acceptance rules and the arbiter.
    pub fn create_milestone(
        ctx: Context<CreateMilestone>,
        milestone_id: u64,
        contractor: Pubkey,
        oracle: Pubkey,
        amount: u64,
        ruleset_hash: [u8; 32],
        deadline: i64,
        arbiter: Pubkey,
        dispute_window: i64,
    ) -> Result<()> {
        require!(amount > 0, EscrowError::ZeroAmount);
        require!(deadline > Clock::get()?.unix_timestamp, EscrowError::DeadlineInPast);
        // Below this a payout to an empty wallet fails forever.
        require!(amount >= Rent::get()?.minimum_balance(0), EscrowError::AmountBelowRentMinimum);
        require!(
            (MIN_DISPUTE_WINDOW..=MAX_DISPUTE_WINDOW).contains(&dispute_window),
            EscrowError::InvalidDisputeWindow
        );
        // An arbiter who is also a party could decide its own dispute.
        let investor = ctx.accounts.investor.key();
        require!(![investor, contractor, oracle].contains(&arbiter), EscrowError::ArbiterNotIndependent);

        let transfer = system_program::Transfer {
            from: ctx.accounts.investor.to_account_info(),
            to: ctx.accounts.milestone.to_account_info(),
        };
        system_program::transfer(CpiContext::new(system_program::ID, transfer), amount)?;

        ctx.accounts.milestone.set_inner(Milestone {
            investor,
            contractor,
            oracle,
            arbiter,
            amount,
            ruleset_hash,
            deadline,
            dispute_window,
            status: Status::Open,
            approved_at: 0,
            disputed_at: 0,
            asset_hash: [0; 32],
            result_hash: [0; 32],
            milestone_id,
            bump: ctx.bumps.milestone,
        });
        Ok(())
    }

    /// Oracle confirms PASS against the frozen ruleset. This opens the dispute window; no money moves.
    pub fn approve(
        ctx: Context<Approve>,
        asset_hash: [u8; 32],
        ruleset_hash: [u8; 32],
        result_hash: [u8; 32],
    ) -> Result<()> {
        let milestone = &mut ctx.accounts.milestone;
        let now = Clock::get()?.unix_timestamp;
        require!(milestone.status == Status::Open, EscrowError::NotOpen);
        require!(now <= milestone.deadline, EscrowError::DeadlinePassed);
        require!(ruleset_hash == milestone.ruleset_hash, EscrowError::RulesetMismatch);

        milestone.asset_hash = asset_hash;
        milestone.result_hash = result_hash;
        milestone.approved_at = now;
        milestone.status = Status::Approved;
        Ok(())
    }

    /// Investor objects to the approval while the window is open. The arbiter decides next.
    pub fn dispute(ctx: Context<Dispute>) -> Result<()> {
        let milestone = &mut ctx.accounts.milestone;
        let now = Clock::get()?.unix_timestamp;
        require!(milestone.status == Status::Approved, EscrowError::NotApproved);
        require!(now <= milestone.approved_at + milestone.dispute_window, EscrowError::DisputeWindowClosed);

        milestone.disputed_at = now;
        milestone.status = Status::Disputed;
        Ok(())
    }

    /// Arbiter decides a dispute in time: pay the contractor or refund the investor, nobody else.
    pub fn resolve(ctx: Context<Resolve>, pay_contractor: bool) -> Result<()> {
        let milestone = &ctx.accounts.milestone;
        require!(milestone.status == Status::Disputed, EscrowError::NotDisputed);
        require!(
            Clock::get()?.unix_timestamp <= milestone.disputed_at + milestone.dispute_window,
            EscrowError::ArbiterPeriodOver
        );

        // Only the winner's account takes part, so the other side cannot block the payout.
        let (winner, wrong, status) = match pay_contractor {
            true => (milestone.contractor, EscrowError::WrongContractor, Status::Released),
            false => (milestone.investor, EscrowError::WrongInvestor, Status::Refunded),
        };
        require_keys_eq!(ctx.accounts.recipient.key(), winner, wrong);
        settle(&mut ctx.accounts.milestone, &ctx.accounts.recipient.to_account_info(), status)
    }

    /// Anyone may pay the contractor once nothing can change the outcome any more: the dispute
    /// window passed without a dispute, or the arbiter did not decide in time.
    pub fn claim(ctx: Context<Claim>) -> Result<()> {
        let milestone = &ctx.accounts.milestone;
        let window_end = match milestone.status {
            Status::Approved => milestone.approved_at + milestone.dispute_window,
            Status::Disputed => milestone.disputed_at + milestone.dispute_window,
            _ => return err!(EscrowError::NotApproved),
        };
        require!(Clock::get()?.unix_timestamp > window_end, EscrowError::ClaimTooEarly);

        settle(&mut ctx.accounts.milestone, &ctx.accounts.contractor.to_account_info(), Status::Released)
    }

    /// After the deadline without an approval, the investor takes the money back.
    pub fn refund(ctx: Context<Refund>) -> Result<()> {
        let milestone = &ctx.accounts.milestone;
        require!(milestone.status == Status::Open, EscrowError::NotOpen);
        require!(Clock::get()?.unix_timestamp > milestone.deadline, EscrowError::DeadlineNotReached);

        settle(&mut ctx.accounts.milestone, &ctx.accounts.investor.to_account_info(), Status::Refunded)
    }
}

/// The only place lamports leave a milestone: the locked amount goes to `recipient` and the
/// status becomes final. The program owns the milestone account, so it may debit it directly.
fn settle<'info>(milestone: &mut Account<'info, Milestone>, recipient: &AccountInfo<'info>, status: Status) -> Result<()> {
    milestone.sub_lamports(milestone.amount)?;
    recipient.add_lamports(milestone.amount)?;
    milestone.status = status;
    Ok(())
}

#[derive(Accounts)]
#[instruction(milestone_id: u64)]
pub struct CreateMilestone<'info> {
    #[account(mut)]
    pub investor: Signer<'info>,
    #[account(
        init,
        payer = investor,
        space = 8 + Milestone::INIT_SPACE,
        seeds = [MILESTONE_SEED, investor.key().as_ref(), &milestone_id.to_le_bytes()],
        bump
    )]
    pub milestone: Account<'info, Milestone>,
    pub system_program: Program<'info, System>,
}

#[derive(Accounts)]
pub struct Approve<'info> {
    pub oracle: Signer<'info>,
    #[account(mut, has_one = oracle @ EscrowError::WrongOracle)]
    pub milestone: Account<'info, Milestone>,
}

#[derive(Accounts)]
pub struct Dispute<'info> {
    pub investor: Signer<'info>,
    #[account(mut, has_one = investor @ EscrowError::WrongInvestor)]
    pub milestone: Account<'info, Milestone>,
}

/// The arbiter can only choose between the two stored parties: `resolve` checks that `recipient`
/// is the contractor (pay) or the investor (refund), never anyone else.
#[derive(Accounts)]
pub struct Resolve<'info> {
    pub arbiter: Signer<'info>,
    #[account(mut, has_one = arbiter @ EscrowError::WrongArbiter)]
    pub milestone: Account<'info, Milestone>,
    /// CHECK: only credited; its address is checked against the milestone in `resolve`. Any owner is
    /// accepted, so a party cannot block the payout by handing its wallet to another program.
    #[account(mut)]
    pub recipient: UncheckedAccount<'info>,
}

/// No signer: whoever pays the fee can trigger it, but the money only goes to the stored contractor.
#[derive(Accounts)]
pub struct Claim<'info> {
    #[account(mut, has_one = contractor @ EscrowError::WrongContractor)]
    pub milestone: Account<'info, Milestone>,
    /// CHECK: only credited; the address is checked by `has_one` above, any owner is accepted.
    #[account(mut)]
    pub contractor: UncheckedAccount<'info>,
}

#[derive(Accounts)]
pub struct Refund<'info> {
    #[account(mut)]
    pub investor: Signer<'info>,
    #[account(mut, has_one = investor @ EscrowError::WrongInvestor)]
    pub milestone: Account<'info, Milestone>,
}
