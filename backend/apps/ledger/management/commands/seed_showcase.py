# -*- coding: utf-8 -*-
"""演示数据：为 README / 演示截图造一段"好看"的家庭账本。

用法：
    python manage.py seed_showcase            # 幂等，已存在则跳过
    python manage.py seed_showcase --reset    # 清空重建

产出：
    · 两个成员账号 + 一个家庭（账本名自定义、含协商阈值）
    · 7 个账户（储蓄卡 / 信用卡 / 现金 / 钱包，三类账本齐全）
    · 近 6 个月、约 200 笔流水（工资、房租、餐饮、出行…含私密消费）
    · 3 笔借钱来往（未还 / 部分还 / 已还清各一）
    · 6 个月账户快照，资产净值曲线呈上升态势
    · 一个已完成的账单导入任务（让导入页有内容）
余额账实相符：账户余额 = 期初余额 + 全部流水净额，期初写入审计日志。
"""
import random
from datetime import datetime, time, timedelta

from django.core.management.base import BaseCommand
from django.db.models import F
from django.utils import timezone

from apps.accounts.models import Account, AccountSnapshot, BalanceAdjustLog
from apps.families.models import DEFAULT_PERMISSIONS, Family, FamilyMember, Threshold
from apps.ledger.models import Category, ImportTask, Transaction
from apps.ledger.services import apply_balance
from apps.loans.services import add_repayment, create_loan
from apps.users.models import User

# 固定种子，保证每次造出来的数据完全一致（截图可复现）
RANDOM_SEED = 20261009
MONTHS = 6

OWNER_PHONE = '13800138000'
SPOUSE_PHONE = '13800138001'
PASSWORD = 'test123456'
OWNER_NICK = '小林'          # 演示用中性称呼，不预设成员关系
SPOUSE_NICK = '小陈'
FAMILY_NAME = '示例家庭'

# 账户：(名称, 图标, 归属, 账本, 介质, 银行, 是否计总资产, 期初余额元)
ACCOUNTS = [
    ('招商银行储蓄卡', '💳', 'owner', 'husband', 'debit', '招商银行', True, 86000),
    ('招行信用卡', '💴', 'owner', 'husband', 'credit', '招商银行', True, -3000),
    ('微信钱包', '💬', 'owner', 'husband', 'wallet', '微信支付', True, 12000),
    ('工商银行储蓄卡', '🏦', 'spouse', 'wife', 'debit', '工商银行', True, 54000),
    ('支付宝', '🅰️', 'spouse', 'wife', 'wallet', '支付宝', True, 20000),
    ('建设银行储蓄卡', '🏠', 'owner', 'shared', 'debit', '建设银行', True, 128000),
    ('家庭现金', '💵', 'owner', 'shared', 'cash', '', True, 800),
]

# (分类, 商户候选, 每月笔数, 单笔金额区间元, 归属人, 账户序号, 是否私密)
EXPENSE_TEMPLATE = [
    ('food', ['海底捞', '瑞幸咖啡', '麦当劳', '美团外卖', '楼下便利店', '星巴克'], 12, (12, 320), 'owner', 0, False),
    ('food', ['饿了么', '喜茶', '肯德基', '公司食堂'], 8, (15, 90), 'spouse', 4, False),
    ('home', ['永辉超市', '大润发', '美团买菜', '京东超市'], 5, (30, 460), 'owner', 5, False),
    ('transport', ['滴滴出行', '地铁', '中石化加油', '停车费'], 6, (8, 300), 'owner', 0, False),
    ('clothing', ['优衣库', '唯品会', 'Nike 专卖店'], 2, (150, 900), 'spouse', 4, False),
    ('entertainment', ['腾讯视频', '网易云音乐', '万达影城', 'Steam'], 3, (15, 260), 'owner', 2, False),
    ('education', ['学而思', '新东方', '钢琴课'], 1, (800, 2600), 'spouse', 3, False),
    ('medical', ['社区医院', '海王星辰', '体检中心'], 1, (60, 680), 'owner', 0, False),
    ('digital', ['Apple Store', '小米之家', '华为旗舰店'], 1, (200, 1200), 'owner', 5, False),
    ('beauty', ['屈臣氏', '丝芙兰'], 1, (120, 780), 'spouse', 4, False),
    ('gift', ['礼物', '红包'], 1, (200, 1200), 'owner', 2, False),
    ('clothing', ['淘宝', '京东'], 2, (60, 350), 'owner', 1, True),       # 成员一私密消费
    ('beauty', ['小红书', '美容院'], 1, (200, 900), 'spouse', 4, True),    # 成员二私密消费
]

INCOME_TEMPLATE = [
    ('salary', ['公司', '月薪'], 1, (18500, 18500), 'owner', 0),
    ('salary', ['公司', '月薪'], 1, (12800, 12800), 'spouse', 3),
    ('investment_income', ['余额宝', '理财通'], 1, (60, 480), 'owner', 0),
    ('bonus', ['项目奖金'], 1, (2000, 6000), 'owner', 0),
    ('freelance', ['接单外快'], 1, (800, 3200), 'spouse', 3),
]


class Command(BaseCommand):
    help = '造一套用于演示/截图的家庭账本数据'

    def add_arguments(self, parser):
        parser.add_argument('--reset', action='store_true', help='清空家庭已有业务数据后重建')

    def handle(self, *args, **options):
        if not Category.objects.exists():
            self.stdout.write(self.style.WARNING('分类为空，请先执行: python manage.py seed_categories'))
            return

        rng = random.Random(RANDOM_SEED)
        owner, spouse, family = self._ensure_family()
        if options['reset']:
            self._reset(family)
        elif Transaction.objects.filter(family=family).exists():
            # 流水/借贷是增量写入的，重复执行会叠加，所以已有数据就直接跳过
            self.stdout.write(self.style.WARNING(
                '演示数据已存在，跳过。如需重建：python manage.py seed_showcase --reset'))
            self._report(family, Account.objects.filter(family=family))
            return

        accounts = self._build_accounts(owner, spouse, family)
        self._build_transactions(owner, spouse, family, accounts, rng)
        self._build_loans(owner, family, accounts, rng)
        self._build_snapshots(accounts, rng)
        self._build_import_task(owner, family)

        self._report(family, accounts)

    # ---------- 基础 ----------
    def _ensure_family(self):
        owner, _ = User.objects.get_or_create(
            username=OWNER_PHONE,
            defaults={'phone': OWNER_PHONE, 'nickname': OWNER_NICK},
        )
        owner.set_password(PASSWORD)
        owner.nickname = OWNER_NICK
        owner.privacy_limit_cents = 80000          # 隐私额度 ¥800，配合私密消费演示
        owner.save(update_fields=['password', 'nickname', 'privacy_limit_cents'])

        spouse, _ = User.objects.get_or_create(
            username=SPOUSE_PHONE,
            defaults={'phone': SPOUSE_PHONE, 'nickname': SPOUSE_NICK},
        )
        spouse.set_password(PASSWORD)
        spouse.nickname = SPOUSE_NICK
        spouse.privacy_limit_cents = 80000
        spouse.save(update_fields=['password', 'nickname', 'privacy_limit_cents'])

        family = Family.objects.filter(owner=owner).first()
        if family is None:
            family = Family.objects.create(owner=owner, name=FAMILY_NAME)
        if family.name in ('我的家庭', ''):
            family.name = FAMILY_NAME
        # 演示「账本名由家庭自己命名」：默认名只是中性占位
        family.book_labels = {'shared': '共同账本', 'husband': f'{OWNER_NICK}的账',
                              'wife': f'{SPOUSE_NICK}的账'}
        family.save(update_fields=['name', 'book_labels'])
        owner_member, _ = FamilyMember.objects.get_or_create(
            family=family, user=owner,
            defaults={'role': FamilyMember.ROLE_OWNER,
                      'nickname': OWNER_NICK,
                      'book_type': FamilyMember.BOOK_HUSBAND})
        spouse_member, _ = FamilyMember.objects.get_or_create(
            family=family, user=spouse,
            defaults={'role': FamilyMember.ROLE_MEMBER,
                      'nickname': SPOUSE_NICK,
                      'book_type': FamilyMember.BOOK_WIFE,
                      'permissions': dict(DEFAULT_PERMISSIONS)})
        # get_or_create 不会更新已有记录，昵称改名后要显式同步（权限保持不动）
        for member, nick in ((owner_member, OWNER_NICK), (spouse_member, SPOUSE_NICK)):
            if member.nickname != nick:
                member.nickname = nick
                member.save(update_fields=['nickname'])
        Threshold.objects.get_or_create(family=family, defaults={
            'small_limit_cents': 80000, 'notify_limit_cents': 300000, 'approve_limit_cents': 800000})
        return owner, spouse, family

    def _reset(self, family):
        Transaction.objects.filter(family=family).delete()
        from apps.loans.models import Loan, LoanRepayment
        LoanRepayment.objects.filter(loan__family=family).delete()
        Loan.objects.filter(family=family).delete()
        AccountSnapshot.objects.filter(account__family=family).delete()
        BalanceAdjustLog.objects.filter(account__family=family).delete()
        Account.objects.filter(family=family).delete()
        ImportTask.objects.filter(family=family).delete()
        self.stdout.write('已清空原有演示数据')

    def _build_accounts(self, owner, spouse, family):
        accounts = []
        for name, icon, who, book, card, bank, count_total, opening in ACCOUNTS:
            user = owner if who == 'owner' else spouse
            account, created = Account.objects.get_or_create(
                family=family, user=user, name=name,
                defaults={'icon': icon, 'type': Account.TYPE_PERSONAL, 'book_type': book,
                          'card_type': card, 'bank_name': bank, 'is_count_total': count_total,
                          'balance_cents': 0},
            )
            if not created:
                # 复用已有账户时归零，重新走一遍期初录入，保证余额与流水对齐
                Account.objects.filter(pk=account.pk).update(balance_cents=0)
                account.refresh_from_db()
            self._opening(account, user, opening * 100)
            accounts.append(account)
        return accounts

    def _opening(self, account, user, cents):
        """期初余额录入：记审计日志，保证"余额 = 期初 + 流水"可追溯。"""
        BalanceAdjustLog.objects.create(account=account, operator=user, before_cents=0,
                                        after_cents=cents, reason='演示数据：期初余额录入')
        Account.objects.filter(pk=account.pk).update(balance_cents=F('balance_cents') + cents)
        account.refresh_from_db()

    # ---------- 流水 ----------
    def _build_transactions(self, owner, spouse, family, accounts, rng):
        today = timezone.localdate()
        created = 0
        for back in range(MONTHS - 1, -1, -1):
            month = (today.replace(day=1) - timedelta(days=31 * back)).replace(day=1)
            days_in_month = self._days_of(month)
            for category, merchants, count, (lo, hi), who, acc_idx, is_private \
                    in EXPENSE_TEMPLATE:
                for _ in range(count):
                    self._add(owner, spouse, family, accounts, rng,
                              who=who, acc_idx=acc_idx, category=category,
                              merchants=merchants, lo=lo, hi=hi,
                              month=month, days=days_in_month,
                              tx_type=Transaction.TYPE_EXPENSE, is_private=is_private)
                    created += 1
            for category, merchants, count, (lo, hi), who, acc_idx in INCOME_TEMPLATE:
                for _ in range(count):
                    self._add(owner, spouse, family, accounts, rng,
                              who=who, acc_idx=acc_idx, category=category,
                              merchants=merchants, lo=lo, hi=hi,
                              month=month, days=days_in_month,
                              tx_type=Transaction.TYPE_INCOME, is_private=False)
                    created += 1
            # 房租：共同账本固定支出，账单页与报告页最显眼的一笔
            self._add(owner, spouse, family, accounts, rng, who='owner', acc_idx=5,
                      category='home', merchants=['房东'], lo=4500, hi=4500,
                      month=month, days=days_in_month, tx_type=Transaction.TYPE_EXPENSE,
                      is_private=False, fixed_day=1, description='每月房租')
            created += 1
        self.stdout.write(f'流水：{created} 笔')

    def _add(self, owner, spouse, family, accounts, rng, *, who, acc_idx, category,
             merchants, lo, hi, month, days, tx_type, is_private,
             fixed_day=None, description=''):
        user = owner if who == 'owner' else spouse
        account = accounts[acc_idx]
        day = fixed_day or rng.randint(1, days)
        # 当前月不生成"未来"的流水
        now = timezone.localdate()
        if month.year == now.year and month.month == now.month and day > now.day:
            day = now.day
        amount = rng.randint(lo * 100, hi * 100) if hi > lo else lo * 100
        moment = timezone.make_aware(datetime.combine(
            month.replace(day=day), time(rng.randint(7, 22), rng.randint(0, 59))))
        tx = Transaction.objects.create(
            family=family, user=user, account=account, type=tx_type,
            amount_cents=amount, category_id=category,
            merchant=rng.choice(merchants), description=description,
            source=Transaction.SOURCE_MANUAL, is_private=is_private,
            transaction_date=moment,
        )
        apply_balance(account, tx_type, amount)
        return tx

    def _days_of(self, month):
        nxt = (month.replace(day=28) + timedelta(days=7)).replace(day=1)
        return (nxt - timedelta(days=1)).day

    # ---------- 借钱来往 ----------
    def _build_loans(self, owner, family, accounts, rng):
        today = timezone.localdate()
        member = FamilyMember.objects.get(family=family, user=owner)
        card = accounts[0]      # 招商银行储蓄卡

        # 1. 借出给朋友，还了一部分 → 部分还
        loan = create_loan(member, owner, direction='lend', party='王哥',
                           amount_cents=2000000, account=card,
                           loan_date=today - timedelta(days=96),
                           due_date=today + timedelta(days=30), note='买房周转')
        add_repayment(loan, owner, amount_cents=800000, account=card,
                      repay_date=today - timedelta(days=30), note='先还一部分')

        # 2. 向父母借入，已还清 → 已还清
        loan2 = create_loan(member, owner, direction='borrow', party='妈妈',
                            amount_cents=3000000, account=card,
                            loan_date=today - timedelta(days=150),
                            due_date=today - timedelta(days=20), note='装修款')
        add_repayment(loan2, owner, amount_cents=3000000, account=card,
                      repay_date=today - timedelta(days=45), note='一次还清')

        # 3. 借给同事，还没还 → 未还
        create_loan(member, owner, direction='lend', party='李姐',
                    amount_cents=500000, account=card,
                    loan_date=today - timedelta(days=12),
                    due_date=today + timedelta(days=60), note='临时周转')
        self.stdout.write('借钱来往：3 笔（未还 / 部分还 / 已还清）')

    # ---------- 快照 ----------
    def _build_snapshots(self, accounts, rng):
        today = timezone.localdate()
        for account in accounts:
            end = account.balance_cents
            # 历史越早余额越低（信用卡则负债越多），让净值曲线整体向上
            start = int(end * rng.uniform(0.62, 0.80)) if end >= 0 else int(end * rng.uniform(1.15, 1.35))
            for back in range(MONTHS - 1, -1, -1):
                ym_date = (today.replace(day=1) - timedelta(days=31 * back)).replace(day=1)
                ym = ym_date.strftime('%Y-%m')
                ratio = (MONTHS - 1 - back) / max(1, MONTHS - 1)
                value = int(start + (end - start) * ratio)
                AccountSnapshot.objects.update_or_create(account=account, ym=ym,
                                                         defaults={'balance_cents': value})
            last_ym = (today.replace(day=1) - timedelta(days=31)).replace(day=1).strftime('%Y-%m')
            last = AccountSnapshot.objects.filter(account=account, ym=last_ym).first()
            Account.objects.filter(pk=account.pk).update(
                last_balance_cents=last.balance_cents if last else account.balance_cents)
            account.refresh_from_db()
        self.stdout.write(f'快照：{AccountSnapshot.objects.count()} 条（{MONTHS} 个月）')

    # ---------- 导入任务 ----------
    def _build_import_task(self, owner, family):
        now = timezone.now()
        ImportTask.objects.get_or_create(
            family=family, user=owner, platform='wechat',
            defaults={
                'status': ImportTask.STATUS_DONE,
                'total_count': 42, 'new_count': 38, 'duplicate_count': 4, 'failed_count': 0,
                'created_at': now - timedelta(days=2),
            },
        )
        self.stdout.write('导入任务：1 条已完成记录')

    # ---------- 输出 ----------
    def _report(self, family, accounts):
        from apps.loans.services import summarize
        total = sum(a.balance_cents for a in accounts if a.is_count_total)
        tx = Transaction.objects.filter(family=family)
        income = sum(t.amount_cents for t in tx if t.type == Transaction.TYPE_INCOME)
        expense = sum(t.amount_cents for t in tx if t.type == Transaction.TYPE_EXPENSE)
        loan = summarize(family)
        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('演示数据就绪'))
        self.stdout.write(f'  登录账号：{OWNER_PHONE} / {PASSWORD}（{OWNER_NICK}）、'
                          f'{SPOUSE_PHONE} / {PASSWORD}（{SPOUSE_NICK}）')
        self.stdout.write(f'  家庭：{family.name}')
        self.stdout.write(f'  账户：{len(accounts)} 个，总资产 ¥{total / 100:,.2f}')
        self.stdout.write(f'  流水：{tx.count()} 笔，收入 ¥{income / 100:,.2f}，支出 ¥{expense / 100:,.2f}')
        self.stdout.write(f'  借贷：待收 ¥{loan["lend_cents"] / 100:,.2f}，待还 ¥{loan["borrow_cents"] / 100:,.2f}')
