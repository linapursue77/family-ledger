# -*- coding: utf-8 -*-
"""管理后台接口（仅 is_staff 可访问）。

设计要点：
1. 与 C 端接口完全隔离在 /console/ 前缀下，权限统一 IsAdminUser，
   业务侧任何「家庭内权限」逻辑都不参与。
2. 统计口径集中在这里，前端只负责展示，避免两端各算一套。
3. 所有写操作都做了自我保护：管理员不能停用自己、不能取消自己的后台权限，
   防止唯一管理员把自己锁在门外。
"""
from datetime import datetime, time, timedelta

from django.contrib.auth import get_user_model
from django.db.models import Count, Q
from django.db.models.functions import TruncDate
from django.utils import timezone
from django_q.models import Schedule, Task
from django_q.tasks import async_task
from rest_framework.permissions import IsAdminUser
from rest_framework.views import APIView

from apps.core.pagination import ApiPagination
from apps.core.response import BusinessError, api_response
from apps.families.models import Family, FamilyMember
from apps.ledger.models import RecurringRule, Transaction
from apps.membership import services as vip
from apps.membership.models import VipPlan, VipSubscription

User = get_user_model()

# 趋势图天数：两周足够看出增长是否停滞，又不至于把卡片撑爆
TREND_DAYS = 14


def _dt(value, fmt='%Y-%m-%d %H:%M'):
    """本地时间格式化；None 原样返回，前端统一按空值处理。"""
    if not value:
        return ''
    return timezone.localtime(value).strftime(fmt)


def _day(value):
    return value.strftime('%Y-%m-%d') if value else ''


def _vip_map(user_ids):
    """批量取每个用户当前生效的会员（到期最晚的一条），避免列表 N+1。"""
    result = {}
    rows = (VipSubscription.objects
            .filter(user_id__in=user_ids, expire_at__gt=timezone.now())
            .select_related('plan')
            .order_by('user_id', '-expire_at'))
    for sub in rows:
        result.setdefault(str(sub.user_id), sub)
    return result


def _member_map(user_ids):
    """批量取用户的家庭成员身份（家庭名 / 角色），一个人通常只有一个家庭。"""
    result = {}
    rows = (FamilyMember.objects
            .filter(user_id__in=user_ids)
            .select_related('family')
            .order_by('joined_at'))
    for m in rows:
        result.setdefault(str(m.user_id), m)
    return result


def _tx_count_map(user_ids):
    """批量取每个用户的记账笔数。"""
    rows = (Transaction.objects
            .filter(user_id__in=user_ids)
            .values('user_id')
            .annotate(n=Count('id')))
    return {str(r['user_id']): r['n'] for r in rows}


# ---------------------------------------------------------------- 概览
class OverviewView(APIView):
    """首页看板：用户、家庭、会员、记账、定时任务五组指标 + 近 14 天趋势。"""

    permission_classes = [IsAdminUser]

    def get(self, request):
        now = timezone.now()
        today = timezone.localdate()
        week_ago = now - timedelta(days=7)
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

        users = User.objects.all()
        active_vip_ids = (VipSubscription.objects
                          .filter(expire_at__gt=now)
                          .values_list('user_id', flat=True).distinct())

        # 活跃用户按「近 7 天记过账」算，比登录活跃更贴近真实使用
        active_users = (Transaction.objects
                        .filter(transaction_date__gte=week_ago)
                        .values('user_id').distinct().count())

        schedules = list(Schedule.objects.order_by('next_run'))
        last_task = Task.objects.order_by('-started').first()
        failed_24h = Task.objects.filter(success=False, started__gte=now - timedelta(hours=24)).count()

        # 近 14 天：注册数 / 记账笔数，按本地日期分桶后补零
        start_day = today - timedelta(days=TREND_DAYS - 1)
        start_dt = timezone.make_aware(datetime.combine(start_day, time.min))
        tz = timezone.get_current_timezone()

        reg_rows = (User.objects.filter(date_joined__gte=start_dt)
                    .annotate(d=TruncDate('date_joined', tzinfo=tz))
                    .values('d').annotate(n=Count('id')))
        tx_rows = (Transaction.objects.filter(transaction_date__gte=start_dt)
                   .annotate(d=TruncDate('transaction_date', tzinfo=tz))
                   .values('d').annotate(n=Count('id')))
        reg_map = {str(r['d']): r['n'] for r in reg_rows}
        tx_map = {str(r['d']): r['n'] for r in tx_rows}
        trend = [
            {
                'date': _day(start_day + timedelta(days=i)),
                'users': reg_map.get(str(start_day + timedelta(days=i)), 0),
                'transactions': tx_map.get(str(start_day + timedelta(days=i)), 0),
            }
            for i in range(TREND_DAYS)
        ]

        data = {
            'users': {
                'total': users.count(),
                'today': users.filter(date_joined__gte=today_start).count(),
                'week': users.filter(date_joined__gte=week_ago).count(),
                'month': users.filter(date_joined__gte=month_start).count(),
                'disabled': users.filter(is_active=False).count(),
                'active_week': active_users,
            },
            'families': {
                'total': Family.objects.count(),
                'multi_member': (Family.objects.annotate(n=Count('members'))
                                 .filter(n__gt=1).count()),
            },
            'vip': {
                'active': active_vip_ids.count(),
                'trial': (VipSubscription.objects
                          .filter(expire_at__gt=now,
                                  source=VipSubscription.SOURCE_TRIAL)
                          .values('user_id').distinct().count()),
                'new_month': (VipSubscription.objects
                              .filter(created_at__gte=month_start, expire_at__gt=now)
                              .values('user_id').distinct().count()),
            },
            'ledger': {
                'transactions': Transaction.objects.count(),
                'month_transactions': Transaction.objects
                .filter(transaction_date__gte=month_start).count(),
                'recurring_rules': RecurringRule.objects.count(),
                'recurring_active': RecurringRule.objects.filter(is_active=True).count(),
            },
            'tasks': {
                'total': len(schedules),
                'enabled': len([s for s in schedules if s.repeats != 0]),
                'failed_24h': failed_24h,
                'last_run_at': _dt(last_task.started) if last_task else '',
                'last_success': bool(last_task.success) if last_task else None,
            },
            'trend': trend,
        }
        return api_response(data)


# ---------------------------------------------------------------- 用户
class UserListView(APIView):
    """注册账号列表：搜索手机号 / 昵称，按状态与会员身份筛选。"""

    permission_classes = [IsAdminUser]

    def get(self, request):
        params = request.query_params
        qs = User.objects.order_by('-date_joined')

        keyword = (params.get('q') or '').strip()
        if keyword:
            qs = qs.filter(Q(phone__icontains=keyword) |
                           Q(nickname__icontains=keyword) |
                           Q(username__icontains=keyword))

        status = params.get('status')
        if status == 'active':
            qs = qs.filter(is_active=True)
        elif status == 'disabled':
            qs = qs.filter(is_active=False)

        now = timezone.now()
        vip_ids = (VipSubscription.objects.filter(expire_at__gt=now)
                   .values_list('user_id', flat=True).distinct())
        vip_flag = params.get('vip')
        if vip_flag == '1':
            qs = qs.filter(id__in=vip_ids)
        elif vip_flag == '0':
            qs = qs.exclude(id__in=vip_ids)

        paginator = ApiPagination()
        page = paginator.paginate_queryset(qs, request)
        ids = [u.id for u in page]

        vip_map = _vip_map(ids)
        member_map = _member_map(ids)
        tx_map = _tx_count_map(ids)

        items = []
        for u in page:
            sub = vip_map.get(str(u.id))
            member = member_map.get(str(u.id))
            items.append({
                'id': str(u.id),
                'phone': u.phone or '',
                'username': u.username,
                'nickname': u.nickname,
                'is_active': u.is_active,
                'is_staff': u.is_staff,
                'date_joined': _dt(u.date_joined),
                'last_login': _dt(u.last_login),
                'family_name': member.family.name if member else '',
                'family_role': member.role if member else '',
                'is_vip': sub is not None,
                'vip_expire_at': _day(sub.expire_at) if sub else '',
                'vip_source': sub.get_source_display() if sub else '',
                'tx_count': tx_map.get(str(u.id), 0),
            })
        return paginator.get_paginated_response(items)


class UserDetailView(APIView):
    """单个账号：资料、家庭、会员历史、记账统计、可执行的管理操作。"""

    permission_classes = [IsAdminUser]

    def get(self, request, user_id):
        user = User.objects.filter(pk=user_id).first()
        if user is None:
            raise BusinessError('用户不存在', code=4004)

        member = (FamilyMember.objects.filter(user=user)
                  .select_related('family').first())
        subs = (VipSubscription.objects.filter(user=user)
                .select_related('plan').order_by('-expire_at')[:20])
        recent = (Transaction.objects.filter(user=user)
                  .select_related('category', 'account')
                  .order_by('-transaction_date')[:10])

        return api_response({
            'user': {
                'id': str(user.id),
                'phone': user.phone or '',
                'username': user.username,
                'nickname': user.nickname,
                'avatar_url': user.avatar_url,
                'is_active': user.is_active,
                'is_staff': user.is_staff,
                'date_joined': _dt(user.date_joined),
                'last_login': _dt(user.last_login),
                'privacy_limit_cents': user.privacy_limit_cents,
            },
            'family': {
                'name': member.family.name if member else '',
                'role': member.role if member else '',
                'joined_at': _dt(member.joined_at) if member else '',
                'member_count': member.family.members.count() if member else 0,
            } if member else None,
            'vip': {
                'is_vip': vip.is_vip(user),
                'expire_at': _day(subs[0].expire_at) if subs else '',
                'source': subs[0].get_source_display() if subs else '',
                'history': [{
                    'id': str(s.id),
                    'plan_name': s.plan.name if s.plan else '',
                    'source': s.get_source_display(),
                    'start_at': _day(s.start_at),
                    'expire_at': _day(s.expire_at),
                    'is_active': s.is_active,
                    'created_at': _dt(s.created_at),
                } for s in subs],
            },
            'stats': {
                'tx_count': Transaction.objects.filter(user=user).count(),
                'month_tx_count': Transaction.objects.filter(
                    user=user,
                    transaction_date__gte=timezone.now().replace(
                        day=1, hour=0, minute=0, second=0, microsecond=0)).count(),
                'account_count': user.accounts.count() if hasattr(user, 'accounts') else 0,
                'recurring_count': RecurringRule.objects.filter(user=user).count(),
            },
            'recent_transactions': [{
                'id': str(t.id),
                'date': _dt(t.transaction_date, '%Y-%m-%d'),
                'type': t.type,
                'amount': t.amount_cents / 100,
                'category': t.category.name if t.category else '',
                'merchant': t.merchant,
            } for t in recent],
        })

    def patch(self, request, user_id):
        user = User.objects.filter(pk=user_id).first()
        if user is None:
            raise BusinessError('用户不存在', code=4004)

        data = request.data or {}
        is_self = str(user.id) == str(request.user.id)

        # 唯一管理员不能把自己锁在门外：这两条是最容易踩的坑
        if is_self and data.get('is_active') is False:
            raise BusinessError('不能停用自己的账号')
        if is_self and data.get('is_staff') is False:
            raise BusinessError('不能取消自己的管理员权限')

        fields = []
        if 'nickname' in data:
            user.nickname = str(data['nickname'])[:50]
            fields.append('nickname')
        if 'is_active' in data:
            user.is_active = bool(data['is_active'])
            fields.append('is_active')
        if 'is_staff' in data:
            user.is_staff = bool(data['is_staff'])
            fields.append('is_staff')
        if fields:
            user.save(update_fields=fields)

        return api_response({
            'id': str(user.id),
            'is_active': user.is_active,
            'is_staff': user.is_staff,
            'nickname': user.nickname,
        }, message='已更新')


# ---------------------------------------------------------------- 会员
class PlanListView(APIView):
    """套餐列表：赠送到期时长时可直接选套餐。"""

    permission_classes = [IsAdminUser]

    def get(self, request):
        items = [{
            'id': str(p.id),
            'code': p.code,
            'name': p.name,
            'price_yuan': p.price_cents / 100,
            'duration_days': p.duration_days,
            'is_active': p.is_active,
        } for p in VipPlan.objects.all()]
        return api_response(items)


class SubscriptionListView(APIView):
    """会员订阅列表 + 手动开通/续期。"""

    permission_classes = [IsAdminUser]

    def get(self, request):
        params = request.query_params
        now = timezone.now()
        qs = VipSubscription.objects.select_related('user', 'plan').order_by('-expire_at')

        keyword = (params.get('q') or '').strip()
        if keyword:
            qs = qs.filter(Q(user__phone__icontains=keyword) |
                           Q(user__nickname__icontains=keyword))

        status = params.get('status')
        if status == 'active':
            qs = qs.filter(expire_at__gt=now)
        elif status == 'expired':
            qs = qs.filter(expire_at__lte=now)

        paginator = ApiPagination()
        page = paginator.paginate_queryset(qs, request)
        items = [{
            'id': str(s.id),
            'user_id': str(s.user_id),
            'phone': s.user.phone or '',
            'nickname': s.user.nickname,
            'plan_name': s.plan.name if s.plan else '手动开通',
            'source': s.get_source_display(),
            'start_at': _day(s.start_at),
            'expire_at': _day(s.expire_at),
            'remain_days': s.remain_days,
            'is_active': s.is_active,
            'created_at': _dt(s.created_at),
        } for s in page]
        return paginator.get_paginated_response(items)

    def post(self, request):
        data = request.data or {}
        user = User.objects.filter(pk=data.get('user_id')).first()
        if user is None:
            raise BusinessError('用户不存在', code=4004)

        plan = None
        if data.get('plan_id'):
            plan = VipPlan.objects.filter(pk=data['plan_id']).first()
            if plan is None:
                raise BusinessError('套餐不存在', code=4004)
            days = plan.duration_days
        else:
            try:
                days = int(data.get('days') or 0)
            except (TypeError, ValueError):
                days = 0

        if days <= 0:
            raise BusinessError('请指定赠送天数或选择套餐')
        if days > 3650:
            raise BusinessError('单次最多赠送 3650 天')

        sub = vip.grant(user, days=days, plan=plan,
                        source=VipSubscription.SOURCE_ADMIN)
        return api_response({
            'id': str(sub.id),
            'expire_at': _day(sub.expire_at),
            'remain_days': sub.remain_days,
        }, message=f'已为 {user.display_name} 开通 {days} 天会员')


class SubscriptionDetailView(APIView):
    """撤销一条开通记录（赠错了用）。"""

    permission_classes = [IsAdminUser]

    def delete(self, request, sub_id):
        sub = VipSubscription.objects.filter(pk=sub_id).first()
        if sub is None:
            raise BusinessError('记录不存在', code=4004)
        user_name = sub.user.display_name
        sub.delete()
        return api_response(None, message=f'已撤销 {user_name} 的这条会员记录')


# ---------------------------------------------------------------- 定时任务
def _task_view(task):
    if task is None:
        return None
    return {
        'started': _dt(task.started),
        'stopped': _dt(task.stopped),
        'success': bool(task.success),
        'result': str(task.result)[:300] if task.result is not None else '',
    }


class ScheduleListView(APIView):
    """django-q 定时任务：排期、上次执行结果、启用状态。"""

    permission_classes = [IsAdminUser]

    def get(self, request):
        items = []
        for s in Schedule.objects.order_by('next_run'):
            last = Task.objects.filter(id=s.task).first() if s.task else None
            items.append({
                'id': s.id,
                'name': s.name or s.func,
                'func': s.func,
                'schedule_type': s.schedule_type,
                'next_run': _dt(s.next_run),
                'enabled': s.repeats != 0,
                'last_task': _task_view(last),
            })
        return api_response(items)


class ScheduleRunView(APIView):
    """立即执行一次（投递到队列，由 qcluster 消费）。"""

    permission_classes = [IsAdminUser]

    def post(self, request, schedule_id):
        s = Schedule.objects.filter(pk=schedule_id).first()
        if s is None:
            raise BusinessError('任务不存在', code=4004)
        task_id = async_task(s.func)
        return api_response({'task_id': task_id}, message='已提交执行，稍后刷新查看结果')


class ScheduleToggleView(APIView):
    """启用 / 停用定时任务。

    django-q 用 repeats 表达：-1 永久重复，0 表示不再触发。
    ★ 停用期间 next_run 会停在过去，重新启用时必须推进到未来，
      否则调度器看到「早就该跑」的排期，行为不可预期。
    """

    permission_classes = [IsAdminUser]

    def patch(self, request, schedule_id):
        s = Schedule.objects.filter(pk=schedule_id).first()
        if s is None:
            raise BusinessError('任务不存在', code=4004)

        enabled = bool((request.data or {}).get('enabled', True))
        if enabled:
            s.repeats = -1
            guard = 0
            while s.next_run and s.next_run < timezone.now() and guard < 400:
                s.next_run = s.calculate_next_run(s.next_run)
                guard += 1
        else:
            s.repeats = 0
        s.save(update_fields=['repeats', 'next_run'])
        return api_response({'enabled': s.repeats != 0,
                             'next_run': _dt(s.next_run)},
                            message='已启用' if enabled else '已停用')


# ---------------------------------------------------------------- 周期记账
class RecurringOverviewView(APIView):
    """全站周期记账规则：管理员能看出用户定时记账是否在正常出账。"""

    permission_classes = [IsAdminUser]

    def get(self, request):
        rules = (RecurringRule.objects
                 .select_related('user', 'family')
                 .order_by('is_active', 'next_run'))
        items = [{
            'id': str(r.id),
            'name': r.name,
            'user': r.user.display_name,
            'family': r.family.name,
            'type': r.type,
            'amount': r.amount_cents / 100,
            'schedule_text': r.schedule_text(),
            'next_run': _day(r.next_run),
            'is_active': r.is_active,
            'run_count': r.run_count,
            'last_run_at': _dt(r.last_run_at),
            'last_error': r.last_error,
        } for r in rules]
        return api_response({
            'items': items,
            'total': len(items),
            'active': len([x for x in items if x['is_active']]),
            'has_error': len([x for x in items if x['last_error']]),
        })
