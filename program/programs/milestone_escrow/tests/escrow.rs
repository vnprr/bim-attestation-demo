//! Program tests on LiteSVM: the happy paths and every rejection case.
//! The clock is set explicitly, so deadline and dispute-window tests need no waiting.

use anchor_lang::{
    prelude::{Clock, Pubkey},
    solana_program::{instruction::Instruction, system_program},
    AccountDeserialize, InstructionData, Space, ToAccountMetas,
};
use litesvm::LiteSVM;
use milestone_escrow::{
    accounts, instruction, EscrowError, Milestone, Status, MAX_DISPUTE_WINDOW, MILESTONE_SEED, MIN_DISPUTE_WINDOW,
};
use solana_keypair::Keypair;
use solana_message::{Message, VersionedMessage};
use solana_signer::Signer;
use solana_transaction::{versioned::VersionedTransaction, InstructionError, TransactionError};

const SOL: u64 = 1_000_000_000;
const AMOUNT: u64 = SOL;
const FEE: u64 = 5_000;
const NOW: i64 = 1_000_000;
const DEADLINE: i64 = NOW + 300;
const WINDOW: i64 = 60;
const DISPUTED_AT: i64 = NOW + 5; // `Env::disputed()` approves at NOW and disputes 5 s later
const STRICT: [u8; 32] = [0xA; 32];
const LENIENT: [u8; 32] = [0xB; 32];
const ASSET: [u8; 32] = [1; 32];
const RESULT: [u8; 32] = [2; 32];

struct Env {
    svm: LiteSVM,
    investor: Keypair,
    contractor: Keypair,
    oracle: Keypair,
    arbiter: Keypair,
    milestone: Pubkey,
}

type TxResult = Result<(), u32>;

impl Env {
    /// Fresh chain with an Open milestone: 1 SOL locked, ruleset STRICT, deadline in 5 min, window 60 s.
    fn new() -> Self {
        let mut env = Self::empty();
        env.create(AMOUNT, DEADLINE).unwrap();
        env
    }

    /// Approved by the oracle at NOW.
    fn approved() -> Self {
        let mut env = Self::new();
        env.approve().unwrap();
        env
    }

    /// Approved at NOW, disputed by the investor at DISPUTED_AT.
    fn disputed() -> Self {
        let mut env = Self::approved();
        env.set_time(DISPUTED_AT);
        env.dispute().unwrap();
        env
    }

    fn empty() -> Self {
        let mut svm = LiteSVM::new();
        let so = include_bytes!(concat!(env!("CARGO_TARGET_TMPDIR"), "/../deploy/milestone_escrow.so"));
        svm.add_program(milestone_escrow::id(), so).unwrap();
        let (investor, contractor, oracle, arbiter) = (Keypair::new(), Keypair::new(), Keypair::new(), Keypair::new());
        for kp in [&investor, &contractor, &oracle, &arbiter] {
            svm.airdrop(&kp.pubkey(), 10 * SOL).unwrap();
        }
        let milestone = Pubkey::find_program_address(
            &[MILESTONE_SEED, investor.pubkey().as_ref(), &7u64.to_le_bytes()],
            &milestone_escrow::id(),
        )
        .0;
        let mut env = Self { svm, investor, contractor, oracle, arbiter, milestone };
        env.set_time(NOW);
        env
    }

    fn set_time(&mut self, unix_timestamp: i64) {
        let mut clock: Clock = self.svm.get_sysvar();
        clock.unix_timestamp = unix_timestamp;
        self.svm.set_sysvar(&clock);
    }

    /// Sends one instruction, `payer` pays the fee and signs; returns the Anchor error code on failure.
    fn send(&mut self, data: impl InstructionData, accounts: impl ToAccountMetas, payer: &Keypair) -> TxResult {
        let ix = Instruction::new_with_bytes(milestone_escrow::id(), &data.data(), accounts.to_account_metas(None));
        self.svm.expire_blockhash(); // identical repeated txs must not be deduplicated
        let msg = Message::new_with_blockhash(&[ix], Some(&payer.pubkey()), &self.svm.latest_blockhash());
        let tx = VersionedTransaction::try_new(VersionedMessage::Legacy(msg), &[payer]).unwrap();
        self.svm.send_transaction(tx).map(|_| ()).map_err(|e| match e.err {
            TransactionError::InstructionError(_, InstructionError::Custom(code)) => code,
            other => panic!("unexpected error: {other:?}"),
        })
    }

    fn create_with(&mut self, amount: u64, deadline: i64, arbiter: Pubkey, dispute_window: i64) -> TxResult {
        let data = instruction::CreateMilestone {
            milestone_id: 7,
            contractor: self.contractor.pubkey(),
            oracle: self.oracle.pubkey(),
            amount,
            ruleset_hash: STRICT,
            deadline,
            arbiter,
            dispute_window,
        };
        let accounts = accounts::CreateMilestone {
            investor: self.investor.pubkey(),
            milestone: self.milestone,
            system_program: system_program::ID,
        };
        let investor = self.investor.insecure_clone();
        self.send(data, accounts, &investor)
    }

    fn create(&mut self, amount: u64, deadline: i64) -> TxResult {
        self.create_with(amount, deadline, self.arbiter.pubkey(), WINDOW)
    }

    fn approve_as(&mut self, oracle: &Keypair, ruleset_hash: [u8; 32]) -> TxResult {
        let data = instruction::Approve { asset_hash: ASSET, ruleset_hash, result_hash: RESULT };
        let accounts = accounts::Approve { oracle: oracle.pubkey(), milestone: self.milestone };
        self.send(data, accounts, oracle)
    }

    fn approve(&mut self) -> TxResult {
        let oracle = self.oracle.insecure_clone();
        self.approve_as(&oracle, STRICT)
    }

    fn dispute_as(&mut self, investor: &Keypair) -> TxResult {
        let accounts = accounts::Dispute { investor: investor.pubkey(), milestone: self.milestone };
        self.send(instruction::Dispute {}, accounts, investor)
    }

    fn dispute(&mut self) -> TxResult {
        let investor = self.investor.insecure_clone();
        self.dispute_as(&investor)
    }

    fn resolve_as(&mut self, arbiter: &Keypair, recipient: Pubkey, pay_contractor: bool) -> TxResult {
        let accounts = accounts::Resolve { arbiter: arbiter.pubkey(), milestone: self.milestone, recipient };
        self.send(instruction::Resolve { pay_contractor }, accounts, arbiter)
    }

    fn resolve(&mut self, pay_contractor: bool) -> TxResult {
        let arbiter = self.arbiter.insecure_clone();
        let recipient = if pay_contractor { self.contractor.pubkey() } else { self.investor.pubkey() };
        self.resolve_as(&arbiter, recipient, pay_contractor)
    }

    /// Claim has no signer of its own; the oracle pays the fee here, as the backend does.
    fn claim_to(&mut self, contractor: Pubkey) -> TxResult {
        let payer = self.oracle.insecure_clone();
        self.send(instruction::Claim {}, accounts::Claim { milestone: self.milestone, contractor }, &payer)
    }

    fn claim(&mut self) -> TxResult {
        self.claim_to(self.contractor.pubkey())
    }

    fn refund_as(&mut self, investor: &Keypair) -> TxResult {
        let accounts = accounts::Refund { investor: investor.pubkey(), milestone: self.milestone };
        self.send(instruction::Refund {}, accounts, investor)
    }

    fn refund(&mut self) -> TxResult {
        let investor = self.investor.insecure_clone();
        self.refund_as(&investor)
    }

    fn state(&self) -> Milestone {
        let account = self.svm.get_account(&self.milestone).unwrap();
        Milestone::try_deserialize(&mut account.data.as_slice()).unwrap()
    }

    fn balance(&self, key: &Pubkey) -> u64 {
        self.svm.get_balance(key).unwrap_or(0)
    }

    /// Hands the account to another program, as its owner can do with one signature. It is then no
    /// longer a plain wallet, but money sent to it must still arrive.
    fn make_non_system(&mut self, key: Pubkey) {
        let mut account = self.svm.get_account(&key).unwrap();
        account.owner = Pubkey::new_unique();
        self.svm.set_account(key, account).unwrap();
    }

    /// A settled milestone keeps exactly its rent-exempt reserve, and nothing moves it again.
    fn assert_settled(&mut self, status: Status) {
        assert_eq!(self.state().status, status);
        let rent = self.svm.minimum_balance_for_rent_exemption(8 + Milestone::INIT_SPACE);
        assert_eq!(self.balance(&self.milestone), rent);
        assert_eq!(self.claim(), code(EscrowError::NotApproved));
        assert_eq!(self.resolve(true), code(EscrowError::NotDisputed));
        assert_eq!(self.refund(), code(EscrowError::NotOpen));
        assert_eq!(self.dispute(), code(EscrowError::NotApproved));
    }
}

fn code(error: EscrowError) -> TxResult {
    Err(error.into())
}

// ---------- create_milestone ----------

#[test]
fn create_locks_funds_and_freezes_terms() {
    let env = Env::new();
    let state = env.state();
    assert_eq!(state.status, Status::Open);
    assert_eq!(state.ruleset_hash, STRICT);
    assert_eq!((state.arbiter, state.dispute_window), (env.arbiter.pubkey(), WINDOW));
    let rent = env.svm.minimum_balance_for_rent_exemption(8 + Milestone::INIT_SPACE);
    assert_eq!(env.balance(&env.milestone), rent + AMOUNT);
}

#[test]
fn create_rejects_zero_amount_and_past_deadline() {
    let mut env = Env::empty();
    assert_eq!(env.create(0, DEADLINE), code(EscrowError::ZeroAmount));
    assert_eq!(env.create(AMOUNT, NOW), code(EscrowError::DeadlineInPast));
}

#[test]
fn create_rejects_amount_below_rent_minimum() {
    let mut env = Env::empty();
    let minimum = env.svm.minimum_balance_for_rent_exemption(0);
    assert_eq!(env.create(minimum - 1, DEADLINE), code(EscrowError::AmountBelowRentMinimum));
}

#[test]
fn create_rejects_invalid_dispute_window() {
    let mut env = Env::empty();
    let arbiter = env.arbiter.pubkey();
    for window in [MIN_DISPUTE_WINDOW - 1, MAX_DISPUTE_WINDOW + 1] {
        assert_eq!(env.create_with(AMOUNT, DEADLINE, arbiter, window), code(EscrowError::InvalidDisputeWindow));
    }
}

#[test]
fn create_rejects_arbiter_who_is_a_party() {
    let mut env = Env::empty();
    for party in [env.investor.pubkey(), env.contractor.pubkey(), env.oracle.pubkey()] {
        assert_eq!(env.create_with(AMOUNT, DEADLINE, party, WINDOW), code(EscrowError::ArbiterNotIndependent));
    }
}

#[test]
fn minimum_amount_can_be_paid_to_an_empty_wallet() {
    let mut env = Env::empty();
    env.contractor = Keypair::new(); // never funded: 0 lamports, account does not exist yet
    let minimum = env.svm.minimum_balance_for_rent_exemption(0);
    env.create(minimum, DEADLINE).unwrap();
    env.approve().unwrap();
    env.set_time(NOW + WINDOW + 1);
    env.claim().unwrap();
    assert_eq!(env.balance(&env.contractor.pubkey()), minimum);
}

// ---------- approve ----------

#[test]
fn approve_stores_hashes_and_moves_no_money() {
    let mut env = Env::new();
    let (contractor, locked) = (env.balance(&env.contractor.pubkey()), env.balance(&env.milestone));
    env.approve().unwrap();

    let state = env.state();
    assert_eq!(state.status, Status::Approved);
    assert_eq!((state.asset_hash, state.result_hash, state.approved_at), (ASSET, RESULT, NOW));
    assert_eq!(env.balance(&env.contractor.pubkey()), contractor);
    assert_eq!(env.balance(&env.milestone), locked);
}

#[test]
fn approve_rejects_different_ruleset() {
    let mut env = Env::new();
    let oracle = env.oracle.insecure_clone();
    assert_eq!(env.approve_as(&oracle, LENIENT), code(EscrowError::RulesetMismatch));
}

#[test]
fn approve_rejects_non_oracle_signer() {
    let mut env = Env::new();
    let impostor = env.contractor.insecure_clone();
    assert_eq!(env.approve_as(&impostor, STRICT), code(EscrowError::WrongOracle));
}

#[test]
fn approve_after_deadline_is_rejected() {
    let mut env = Env::new();
    env.set_time(DEADLINE + 1);
    assert_eq!(env.approve(), code(EscrowError::DeadlinePassed));
}

#[test]
fn approve_twice_is_rejected() {
    let mut env = Env::approved();
    assert_eq!(env.approve(), code(EscrowError::NotOpen));
}

// ---------- claim ----------

#[test]
fn claim_pays_contractor_only_after_the_dispute_window() {
    let mut env = Env::approved();
    let before = env.balance(&env.contractor.pubkey());
    env.set_time(NOW + WINDOW); // last second the investor may still dispute
    assert_eq!(env.claim(), code(EscrowError::ClaimTooEarly));

    env.set_time(NOW + WINDOW + 1);
    env.claim().unwrap();
    assert_eq!(env.balance(&env.contractor.pubkey()), before + AMOUNT);
    env.assert_settled(Status::Released);
}

#[test]
fn claim_on_open_milestone_is_rejected() {
    let mut env = Env::new();
    assert_eq!(env.claim(), code(EscrowError::NotApproved));
}

#[test]
fn claim_rejects_other_wallet() {
    let mut env = Env::approved();
    env.set_time(NOW + WINDOW + 1);
    assert_eq!(env.claim_to(Keypair::new().pubkey()), code(EscrowError::WrongContractor));
}

// ---------- dispute ----------

#[test]
fn dispute_is_possible_until_the_window_ends() {
    let mut env = Env::approved();
    env.set_time(NOW + WINDOW);
    env.dispute().unwrap();
    assert_eq!((env.state().status, env.state().disputed_at), (Status::Disputed, NOW + WINDOW));

    let mut late = Env::approved();
    late.set_time(NOW + WINDOW + 1);
    assert_eq!(late.dispute(), code(EscrowError::DisputeWindowClosed));
}

#[test]
fn dispute_by_other_signer_is_rejected() {
    let mut env = Env::approved();
    let stranger = env.contractor.insecure_clone();
    assert_eq!(env.dispute_as(&stranger), code(EscrowError::WrongInvestor));
}

#[test]
fn dispute_on_open_milestone_is_rejected() {
    let mut env = Env::new();
    assert_eq!(env.dispute(), code(EscrowError::NotApproved));
}

// ---------- resolve ----------

#[test]
fn resolve_for_contractor_pays_contractor() {
    let mut env = Env::disputed();
    let before = env.balance(&env.contractor.pubkey());
    env.resolve(true).unwrap();
    assert_eq!(env.balance(&env.contractor.pubkey()), before + AMOUNT);
    env.assert_settled(Status::Released);
}

#[test]
fn resolve_for_investor_refunds_investor() {
    let mut env = Env::disputed();
    let before = env.balance(&env.investor.pubkey());
    env.resolve(false).unwrap();
    assert_eq!(env.balance(&env.investor.pubkey()), before + AMOUNT); // the arbiter paid the fee
    env.assert_settled(Status::Refunded);
}

#[test]
fn resolve_rejects_non_arbiter_signer() {
    let mut env = Env::disputed();
    let investor = env.investor.insecure_clone();
    assert_eq!(env.resolve_as(&investor, investor.pubkey(), false), code(EscrowError::WrongArbiter));
}

#[test]
fn resolve_cannot_send_money_anywhere_else() {
    let mut env = Env::disputed();
    let (arbiter, contractor, investor) = (env.arbiter.insecure_clone(), env.contractor.pubkey(), env.investor.pubkey());
    let thief = Keypair::new().pubkey();
    assert_eq!(env.resolve_as(&arbiter, thief, true), code(EscrowError::WrongContractor));
    assert_eq!(env.resolve_as(&arbiter, thief, false), code(EscrowError::WrongInvestor));
    // the decision and the recipient must match: "pay" cannot go to the investor, "refund" not to the contractor
    assert_eq!(env.resolve_as(&arbiter, investor, true), code(EscrowError::WrongContractor));
    assert_eq!(env.resolve_as(&arbiter, contractor, false), code(EscrowError::WrongInvestor));
}

#[test]
fn resolve_without_dispute_is_rejected() {
    let mut env = Env::approved();
    assert_eq!(env.resolve(false), code(EscrowError::NotDisputed));
}

#[test]
fn silent_arbiter_means_the_approval_stands() {
    let mut env = Env::disputed();
    env.set_time(DISPUTED_AT + WINDOW); // last second the arbiter may still decide
    assert_eq!(env.claim(), code(EscrowError::ClaimTooEarly));

    env.set_time(DISPUTED_AT + WINDOW + 1);
    assert_eq!(env.resolve(false), code(EscrowError::ArbiterPeriodOver));
    env.claim().unwrap();
    env.assert_settled(Status::Released);
}

#[test]
fn contractor_cannot_freeze_a_lost_dispute() {
    let mut env = Env::disputed();
    let (contractor, investor) = (env.contractor.pubkey(), env.investor.pubkey());
    env.make_non_system(contractor); // the contractor expects to lose and tries to block the refund
    let before = env.balance(&investor);
    env.resolve(false).unwrap();
    assert_eq!(env.balance(&investor), before + AMOUNT);
}

#[test]
fn non_system_parties_can_still_be_paid() {
    let mut env = Env::approved();
    let contractor = env.contractor.pubkey();
    env.make_non_system(contractor);
    let before = env.balance(&contractor);
    env.set_time(NOW + WINDOW + 1);
    env.claim().unwrap();
    assert_eq!(env.balance(&contractor), before + AMOUNT);

    let mut disputed = Env::disputed();
    let investor = disputed.investor.pubkey();
    disputed.make_non_system(investor);
    disputed.resolve(true).unwrap();
    assert_eq!(disputed.state().status, Status::Released);
}

#[test]
fn deadline_limits_only_approval_and_refund() {
    let mut env = Env::new();
    env.set_time(DEADLINE); // approval on the last allowed second
    env.approve().unwrap();
    env.set_time(DEADLINE + 30);
    assert_eq!(env.refund(), code(EscrowError::NotOpen)); // an approved delivery cannot be refunded
    env.dispute().unwrap();
    env.set_time(DEADLINE + 60);
    env.resolve(true).unwrap();
    assert_eq!(env.state().status, Status::Released);
}

// ---------- refund ----------

#[test]
fn refund_before_deadline_is_rejected() {
    let mut env = Env::new();
    env.set_time(DEADLINE);
    assert_eq!(env.refund(), code(EscrowError::DeadlineNotReached));
}

#[test]
fn refund_by_other_signer_is_rejected() {
    let mut env = Env::new();
    env.set_time(DEADLINE + 1);
    let stranger = env.contractor.insecure_clone();
    assert_eq!(env.refund_as(&stranger), code(EscrowError::WrongInvestor));
}

#[test]
fn refund_after_deadline_returns_funds() {
    let mut env = Env::new();
    let before = env.balance(&env.investor.pubkey());
    env.set_time(DEADLINE + 1);
    env.refund().unwrap();

    assert_eq!(env.balance(&env.investor.pubkey()), before + AMOUNT - FEE);
    assert_eq!(env.approve(), code(EscrowError::NotOpen));
    env.assert_settled(Status::Refunded);
}
