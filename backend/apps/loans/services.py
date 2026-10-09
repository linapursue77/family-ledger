# -*- coding: utf-8 -*-
"""借款写操作：余额联动、状态收敛、流水同步都集中在这里，视图只做参数与响应。"""
from datetime import datetime, time

from django.db import transaction as db_transaction
from django.db.models import F, Sum
from django.utils import timezone

from apps.accounts.models import Account, AccountSnapshot
from apps.accounts.services import visible_accounts
from apps.core.response import BusinessError
from apps.ledger.models import Transaction
from apps.loans.models import Loan, LoanRepayment


def adjust_balance(account, delta_cents: int):
    """改余额并刷新当月快照，与账户页手动调整保持同一口径。"""
    if account is None or not delta_cents:
        return
    # 用 F 表达式而不是读回的值相加，避免两人同时记一笔时相互覆盖
    Account.objects.filter(pk=account.pk).update(
        balance_cents=F('balance_cents') + int(delta_cents))
    account.refresh_from_db()
    AccountSnapshot.objects.update_or_create(
        account=account,
        ym=timezone.localdate().strftime('%Y-%m'),
        defaults={'balance_cents': account.balance_cents},
    )


def _noon(day):
    """借款按天记录，落到当天正午，避免时区边界把它挤到前一天或后一天。"""
    return timezone.make_aware(datetime.combine(day, time(12, 0)))


def _loan_tx(loan, user, account, delta_cents, moment, description):
    """借贷同步写一条流水：金额恒正，方向由 loan_in / loan_out 表达。

    ★ 这类流水只是账本的「可见性投影」—— 余额已经由 adjust_balance 改过，
      任何路径都不得再对它做冲正；删除时直接删行，不走账单删除逻辑。
    """
    return Transaction.objects.create(
        family=loan.family,
        user=user,
        account=account,
        type=Transaction.TYPE_LOAN_IN if delta_cents > 0 else Transaction.TYPE_LOAN_OUT,
        amount_cents=abs(int(delta_cents)),
        merchant=loan.party[:100],
        description=description[:255],
        transaction_date=moment,
        loan_id=loan.id,
        source=Transaction.SOURCE_MANUAL,
    )


def _drop_tx(tx_id):
    """只允许删借贷自己生成的流水，加 loan_id 条件兜底，防止误删普通记账。"""
    if tx_id:
        Transaction.objects.filter(id=tx_id, loan_id__gt='').delete()


def resolve_account(member, user, account_id):
    """账户必须属于本家庭且对本人可见（他人「仅本人可见」的账户不能拿来记账）。"""
    if not account_id:
        return None
    account = visible_accounts(member.family, user).filter(id=account_id).first()
    if account is None:
        raise BusinessError('账户不存在或无权使用该账户', code=4001)
    return account


def repaid_of(loan) -> int:
    value = getattr(loan, 'repaid_cents', None)
    if value is None:
        value = loan.repayments.aggregate(s=Sum('amount_cents'))['s'] or 0
    return int(value or 0)


def remaining_of(loan) -> int:
    return max(0, int(loan.amount_cents) - repaid_of(loan))


def status_of(loan) -> str:
    repaid = repaid_of(loan)
    if repaid <= 0:
        return Loan.STATUS_PENDING
    if repaid >= int(loan.amount_cents):
        return Loan.STATUS_SETTLED
    return Loan.STATUS_PARTIAL


def is_overdue(loan) -> bool:
    return bool(loan.due_date and loan.due_date < timezone.localdate()
                and status_of(loan) != Loan.STATUS_SETTLED)


@db_transaction.atomic
def create_loan(member, user, *, direction, party, amount_cents, account,
                loan_date, due_date, note) -> Loan:
    loan = Loan.objects.create(
        family=member.family,
        user=user,
        account=account,
        direction=direction,
        party=party,
        amount_cents=amount_cents,
        loan_date=loan_date or timezone.localdate(),
        due_date=due_date,
        note=note,
    )
    adjust_balance(loan.account, loan.balance_delta_cents)
    desc = f'借出给{loan.party}' if loan.direction == Loan.DIRECTION_LEND else f'向{loan.party}借入'
    if loan.note:
        desc += f'｜{loan.note}'
    tx = _loan_tx(loan, user, loan.account, loan.balance_delta_cents,
                  _noon(loan.loan_date), desc)
    loan.tx_id = tx.id
    loan.save(update_fields=['tx_id', 'updated_at'])
    return loan


@db_transaction.atomic
def add_repayment(loan, user, *, amount_cents, account, repay_date, note) -> LoanRepayment:
    left = remaining_of(loan)
    if amount_cents > left:
        raise BusinessError(f'本次还款超出剩余金额 ¥{left / 100:.2f}', code=4001)
    repayment = LoanRepayment.objects.create(
        loan=loan,
        account=account or loan.account,
        amount_cents=amount_cents,
        repay_date=repay_date or timezone.localdate(),
        note=note,
        operator=user,
    )
    delta = loan.repayment_delta_cents(amount_cents)
    adjust_balance(repayment.account, delta)
    desc = (f'收到{loan.party}还款' if loan.direction == Loan.DIRECTION_LEND
            else f'归还{loan.party}借款')
    if repayment.note:
        desc += f'｜{repayment.note}'
    tx = _loan_tx(loan, user, repayment.account, delta, _noon(repayment.repay_date), desc)
    repayment.tx_id = tx.id
    repayment.save(update_fields=['tx_id'])
    return repayment


@db_transaction.atomic
def remove_loan(loan):
    """删借款：还过款的不让删，否则余额对不上账。"""
    if loan.repayments.exists():
        raise BusinessError('这笔借款已有还款记录，请先撤销还款再删除')
    adjust_balance(loan.account, -loan.balance_delta_cents)
    Transaction.objects.filter(loan_id=loan.id).delete()
    loan.delete()


@db_transaction.atomic
def remove_repayment(repayment):
    loan = repayment.loan
    adjust_balance(repayment.account, -loan.repayment_delta_cents(repayment.amount_cents))
    _drop_tx(repayment.tx_id)
    repayment.delete()


def summarize(family) -> dict:
    """家庭借贷总览：谁欠我多少、我欠谁多少、净额与逾期。"""
    rows = (Loan.objects.filter(family=family)
            .annotate(repaid=Sum('repayments__amount_cents'))
            .values('direction', 'amount_cents', 'repaid', 'due_date'))
    today = timezone.localdate()
    lend_total = borrow_total = 0
    lend_count = borrow_count = overdue_count = settled_count = 0
    for row in rows:
        repaid = int(row['repaid'] or 0)
        remaining = max(0, int(row['amount_cents']) - repaid)
        due = row['due_date']
        if remaining == 0:
            settled_count += 1
        elif due and due < today:
            overdue_count += 1
        if row['direction'] == Loan.DIRECTION_LEND:
            lend_total += remaining
            lend_count += 1 if remaining else 0
        else:
            borrow_total += remaining
            borrow_count += 1 if remaining else 0
    return {
        'lend_cents': lend_total,
        'lend_amount': _yuan(lend_total),
        'lend_count': lend_count,
        'borrow_cents': borrow_total,
        'borrow_amount': _yuan(borrow_total),
        'borrow_count': borrow_count,
        'net_cents': lend_total - borrow_total,
        'net_amount': _yuan(lend_total - borrow_total),
        'overdue_count': overdue_count,
        'settled_count': settled_count,
    }


def _yuan(cents: int) -> float:
    return round(int(cents) / 100, 2)
