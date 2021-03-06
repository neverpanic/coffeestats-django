from hashlib import md5
from datetime import timedelta
from calendar import monthrange
from StringIO import StringIO
import csv

from django.core.mail import EmailMessage
from django.db import (
    connection,
    models,
)
from django.conf import settings
from django.core.urlresolvers import reverse
from django.utils import timezone
from django.utils.translation import ugettext as _
from django.contrib.auth.models import (
    AbstractUser,
    BaseUserManager,
)

from model_utils import Choices
from model_utils.fields import AutoCreatedField


DRINK_TYPES = Choices(
    (0, 'coffee', _('Coffee')),
    (1, 'mate', _('Mate')),
)

ACTION_TYPES = Choices(
    (0, 'change_email', _('Change email')),
)

WEEKDAY_LABELS = (
    _('Mon'), _('Tue'), _('Wed'), _('Thu'), _('Fri'), _('Sat'), _('Sun')
)


class CaffeineUserManager(BaseUserManager):

    def _create_user(self, username, email, password, **kwargs):
        if not username:
            raise ValueError(_("User must have a username."))
        if not email:
            raise ValueError(_("User must have an email address."))

        user = self.model(
            username=username,
            email=self.normalize_email(email),
            **kwargs)
        if password is not None:
            user.set_password(password)
            # on the run token
            # TODO: use something better for API authentication
            user.token = md5(username + password).hexdigest()
        user.date_joined = timezone.now()
        user.save(using=self.db)
        return user

    def create_user(self, username, email, password=None):
        """
        Creates and saves a User with the given user name, email addresse and
        password.

        :param str username: the user name
        :param str email: the email address
        :param str password: the password
        :returns: User instance

        """
        return self._create_user(username, email, password)

    def create_superuser(self, username, email, password):
        """
        Creates and saves a superuser with the given user name, email address
        and password.

        """
        return self._create_user(
            username, email, password, is_superuser=True, is_staff=True)

    def random_users(self, count=4):
        users = self.raw(
            '''
            SELECT u.*,
            (SELECT COUNT(id) FROM caffeine_caffeine
             WHERE u.id=user_id AND ctype={0:d}) AS coffees,
            (SELECT COUNT(id) FROM caffeine_caffeine
             WHERE u.id=user_id AND ctype={1:d}) AS mate
            FROM caffeine_user u ORDER BY RANDOM() LIMIT {2:d}
            '''.format(DRINK_TYPES.coffee, DRINK_TYPES.mate, count))
        return users

    def recently_joined(self, count=5):
        return self.order_by('-date_joined')[:count]

    def longest_joined(self, count=5):
        return self.order_by('date_joined')[:count]


class User(AbstractUser):
    """
    User model.

    """
    cryptsum = models.CharField(_('old password hash'),
                                max_length=60, blank=True)
    location = models.CharField(max_length=128, blank=True)
    public = models.BooleanField(default=True)
    token = models.CharField(max_length=32, unique=True)
    timezone = models.CharField(_('timezone'), max_length=40,
                                db_index=True, blank=True)

    objects = CaffeineUserManager()

    def get_absolute_url(self):
        return reverse("public", kwargs={'username': self.username})

    def __unicode__(self):
        return self.get_full_name() or self.username

    def export_csv(self):
        subject = _('Your caffeine records')
        body = _('Attached is your caffeine track record.')
        email = EmailMessage(subject, body, to=[self.email])
        now = timezone.now().strftime(settings.CAFFEINE_DATETIME_FORMAT)
        for drink in ('coffee', 'mate'):
            email.attachments.append(
                ('%s-%s.csv' % (drink, now),
                 Caffeine.objects.get_csv_data(
                     getattr(DRINK_TYPES, drink), self),
                 'text/csv'))
        email.send()


def _total_result_dict():
    return {
        DRINK_TYPES.mate: 0,
        DRINK_TYPES.coffee: 0,
    }


def _hour_result_dict():
    return {
        'labels': [unicode(i) for i in range(24)],
        'coffee': [0 for i in range(24)],
        'mate': [0 for i in range(24)],
        'maxvalue': 1,
    }


def _month_result_dict(date):
    result = {
        'labels': [unicode(i + 1) for i in range(monthrange(
            date.year, date.month)[1])],
    }
    result.update({
        'coffee': [0 for i in range(len(result['labels']))],
        'mate': [0 for i in range(len(result['labels']))],
        'maxvalue': 1,
    })
    return result


def _year_result_dict():
    return {
        'labels': [unicode(i + 1) for i in range(12)],
        'coffee': [0 for i in range(12)],
        'mate': [0 for i in range(12)],
        'maxvalue': 1,
    }


def _weekdaily_result_dict():
    result = {
        'labels': WEEKDAY_LABELS,
    }
    result.update({
        'coffee': [0 for i in range(len(result['labels']))],
        'mate': [0 for i in range(len(result['labels']))],
        'maxvalue': 1,
    })
    return result


class CaffeineManager(models.Manager):
    """
    Manager class for Caffeine.

    """
    def total_caffeine_for_user(self, user):
        """
        Return total caffeine for user profile.

        :param User user: user instance
        :return: result dictionary
        """
        result = _total_result_dict()
        cursor = connection.cursor()
        cursor.execute(
            """
            SELECT COUNT(ctype), ctype
            FROM caffeine_caffeine
            WHERE user_id = %s
            GROUP BY ctype
            """, [user.id])
        for ctcount, ctype in cursor.fetchall():
            result[ctype] = ctcount
        return result

    def total_caffeine(self):
        """
        Return total caffeine for all users.

        :return: result dictionary
        """
        result = _total_result_dict()
        cursor = connection.cursor()
        cursor.execute(
            """
            SELECT COUNT(ctype), ctype
            FROM caffeine_caffeine
            GROUP BY ctype
            """, [])
        for ctcount, ctype in cursor.fetchall():
            result[ctype] = ctcount
        return result

    def latest_caffeine_for_user(self, user, count=10):
        """
        Return the latest caffeine entries for the given user.

        :param User user: user instance
        :param int count: number of entries
        :return: list of Caffeine instances
        """
        return self.filter(user=user).order_by('-entrytime')[:count]

    def hourly_caffeine_for_user(self, user):
        """
        Return series of hourly coffees and mate on current day for user
        profile.

        :param User user: user instance
        :return: result dictionary
        """
        result = _hour_result_dict()
        cursor = connection.cursor()
        cursor.execute(
            """
            SELECT ctype, COUNT(id) AS value,
                   date_part('hour', date) AS hour
            FROM   caffeine_caffeine
            WHERE  date_trunc('day', CURRENT_TIMESTAMP) =
                   date_trunc('day', date)
                   AND user_id = %s
            GROUP BY hour, ctype
            """, [user.id])
        for ctype, value, hour in cursor.fetchall():
            result['maxvalue'] = max(value, result['maxvalue'])
            result[DRINK_TYPES._triples[ctype][1]][int(hour)] = value
        return result

    def hourly_caffeine(self):
        """
        Return series of hourly coffees and mate on current day for all users.

        :return: result dictionary
        """
        result = _hour_result_dict()
        cursor = connection.cursor()
        cursor.execute(
            """
            SELECT ctype, COUNT(id) AS value,
                   date_part('hour', date) AS hour
            FROM   caffeine_caffeine
            WHERE  date_trunc('day', CURRENT_TIMESTAMP) =
                   date_trunc('day', date)
            GROUP BY hour, ctype
            """, [])
        for ctype, value, hour in cursor.fetchall():
            result['maxvalue'] = max(value, result['maxvalue'])
            result[DRINK_TYPES._triples[ctype][1]][int(hour)] = value
        return result

    def daily_caffeine_for_user(self, user):
        """
        Return series of daily coffees and mate in current month for user
        profile.

        :param User user: user instance
        :return: result dictionary
        """
        result = _month_result_dict(timezone.now())
        cursor = connection.cursor()
        cursor.execute(
            """
            SELECT ctype, COUNT(id) AS value,
                   date_part('day', date) AS day
            FROM   caffeine_caffeine
            WHERE  date_trunc('month', CURRENT_TIMESTAMP) =
                   date_trunc('month', date)
                   AND user_id = %s
            GROUP BY day, ctype
            """, [user.id])
        for ctype, value, day in cursor.fetchall():
            result['maxvalue'] = max(value, result['maxvalue'])
            result[DRINK_TYPES._triples[ctype][1]][int(day) - 1] = value
        return result

    def daily_caffeine(self):
        """
        Return series of daily coffees and mate in current month for all users.

        :return: result dictionary
        """
        result = _month_result_dict(timezone.now())
        cursor = connection.cursor()
        cursor.execute(
            """
            SELECT ctype, COUNT(id) AS value,
                   date_part('day', date) AS day
            FROM   caffeine_caffeine
            WHERE  date_trunc('month', CURRENT_TIMESTAMP) =
                   date_trunc('month', date)
            GROUP BY day, ctype
            """, [])
        for ctype, value, day in cursor.fetchall():
            result['maxvalue'] = max(value, result['maxvalue'])
            result[DRINK_TYPES._triples[ctype][1]][int(day) - 1] = value
        return result

    def monthly_caffeine_for_user(self, user):
        """
        Return a series of monthly coffees and mate in the current month for
        user profile.

        :param User user: user instance
        :return: result dictionary
        """
        result = _year_result_dict()
        cursor = connection.cursor()
        cursor.execute(
            """
            SELECT ctype, COUNT(id) AS value,
                   date_part('month', date) AS month
            FROM   caffeine_caffeine
            WHERE  date_trunc('year', CURRENT_TIMESTAMP) =
                   date_trunc('year', date)
                   AND user_id = %s
            GROUP BY month, ctype
            """, [user.id])
        for ctype, value, month in cursor.fetchall():
            result['maxvalue'] = max(value, result['maxvalue'])
            result[DRINK_TYPES._triples[ctype][1]][int(month) - 1] = value
        return result

    def monthly_caffeine_overall(self):
        """
        Return a series of monthly coffees and mate in the current month for
        all users.

        :return: result dictionary
        """
        result = _year_result_dict()
        cursor = connection.cursor()
        cursor.execute(
            """
            SELECT ctype, COUNT(id) AS value,
                   date_part('month', date) AS month
            FROM   caffeine_caffeine
            WHERE  date_trunc('year', CURRENT_TIMESTAMP) =
                   date_trunc('year', date)
            GROUP BY month, ctype
            """, [])
        for ctype, value, month in cursor.fetchall():
            result['maxvalue'] = max(value, result['maxvalue'])
            result[DRINK_TYPES._triples[ctype][1]][int(month) - 1] = value
        return result

    def hourly_caffeine_for_user_overall(self, user):
        """
        Return a series of hourly caffeinated drinks for the whole timespan of
        a user's membership.

        :param User user: user instance
        :return: result dictionary
        """
        result = _hour_result_dict()
        cursor = connection.cursor()
        cursor.execute(
            """
            SELECT ctype, COUNT(id) AS value,
                   date_part('hour', date) AS hour
            FROM   caffeine_caffeine
            WHERE  user_id = %s
            GROUP BY hour, ctype
            """, [user.id])
        for ctype, value, hour in cursor.fetchall():
            result['maxvalue'] = max(value, result['maxvalue'])
            result[DRINK_TYPES._triples[ctype][1]][int(hour)] = value
        return result

    def hourly_caffeine_overall(self):
        """
        Return a series of hourly caffeinated drinks for the whole lifetime of
        the site.

        :return: result dictionary
        """
        result = _hour_result_dict()
        cursor = connection.cursor()
        cursor.execute(
            """
            SELECT ctype, COUNT(id) AS value,
                   date_part('hour', date) AS hour
            FROM   caffeine_caffeine
            GROUP BY hour, ctype
            """, [])
        for ctype, value, hour in cursor.fetchall():
            result['maxvalue'] = max(value, result['maxvalue'])
            result[DRINK_TYPES._triples[ctype][1]][int(hour)] = value
        return result

    def weekdaily_caffeine_for_user_overall(self, user):
        """
        Return a series of caffeinated drinks per weekday for the whole
        timespan of a user's membership.

        :param User user: user instance
        :return: result dictionary
        """
        result = _weekdaily_result_dict()
        cursor = connection.cursor()
        cursor.execute(
            """
            SELECT ctype, COUNT(id) AS value,
                   date_part('isodow', date)::int AS wday
            FROM   caffeine_caffeine
            WHERE  user_id = %s
            GROUP BY wday, ctype
            """, [user.id])
        for ctype, value, wday in cursor.fetchall():
            result['maxvalue'] = max(value, result['maxvalue'])
            result[DRINK_TYPES._triples[ctype][1]][wday - 1] = value
        return result

    def weekdaily_caffeine_overall(self):
        """
        Return a series of caffeinated drinks per weekday for the whole
        lifetime of the site.

        :return: result dictionary
        """
        result = _weekdaily_result_dict()
        cursor = connection.cursor()
        cursor.execute(
            """
            SELECT ctype, COUNT(id) AS value,
                   date_part('isodow', date)::int AS wday
            FROM   caffeine_caffeine
            GROUP BY wday, ctype
            """, [])
        for ctype, value, wday in cursor.fetchall():
            if wday is not None:
                result['maxvalue'] = max(value, result['maxvalue'])
                result[DRINK_TYPES._triples[ctype][1]][wday - 1] = value
        return result

    def find_recent_caffeine(self, user, date, ctype):
        caffeines = self.filter(
            user=user, ctype=ctype,
            date__gte=(date - timedelta(
                minutes=settings.MINIMUM_DRINK_DISTANCE)))
        try:
            return caffeines.latest('date')
        except Caffeine.DoesNotExist:
            return False

    def latest_caffeine_activity(self, count=10):
        return self.order_by('-date').select_related('user')[:count].all()

    def top_consumers_total(self, ctype, count=10):
        q = self.filter(ctype=ctype).select_related('user').values_list(
            'user').annotate(caffeine_count=models.Count('id')).order_by(
            '-caffeine_count')[:count]
        users = User.objects.in_bulk([user for user, caffeine_count in q])
        result = []
        for user_id, caffeine_count in q:
            result.append({'user': users[user_id],
                           'caffeine_count': caffeine_count})
        return result

    def top_consumers_average(self, ctype, count=10):
        result = []
        cursor = connection.cursor()
        cursor.execute(
            """
            SELECT c.user_id,
                   COUNT(c.id) /
                   (date_part(
                       'day',
                       (CURRENT_DATE - MIN(c.date))) + 1) AS average
            FROM   caffeine_caffeine c JOIN caffeine_user u ON
                   c.user_id = u.id
            WHERE  c.ctype = %s
            GROUP BY c.user_id
            ORDER BY average DESC
            LIMIT %s
            """, [ctype, count])
        q = cursor.fetchall()
        users = User.objects.in_bulk([row[0] for row in q])
        for user_id, average in q:
            result.append({'user': users[user_id],
                           'average': average})
        return result

    def get_csv_data(self, drinktype, user):
        """
        Get user records for a specific drink type in CSV format.

        :param str drinktype: drink type
        :param User user: user instance
        :return: list of records in CSV format
        """
        csvbuf = StringIO()
        writer = csv.writer(csvbuf)
        writer.writerow(['Timestamp'])
        for row in self.filter(user=user,
                               ctype=drinktype).order_by('date'):
            writer.writerow([
                row.date.strftime(settings.CAFFEINE_DATETIME_FORMAT)])
        retval = csvbuf.getvalue()
        csvbuf.close()
        return retval


class Caffeine(models.Model):
    """
    Caffeinated drink model.

    """
    ctype = models.PositiveSmallIntegerField(choices=DRINK_TYPES,
                                             db_index=True)
    user = models.ForeignKey('User')
    date = models.DateTimeField(_('consumed'), db_index=True)
    entrytime = AutoCreatedField(_('entered'), db_index=True)
    timezone = models.CharField(max_length=40, db_index=True,
                                blank=True)

    objects = CaffeineManager()

    class Meta:
        ordering = ['-date']

    def __unicode__(self):
        return (
            "%s at %s %s" % (
                DRINK_TYPES[self.ctype],
                self.date.strftime(settings.CAFFEINE_DATETIME_FORMAT),
                self.timezone or "")).strip()

    def format_type(self):
        return DRINK_TYPES[self.ctype]


class ActionManager(models.Manager):
    """
    Manager class for actions.

    """
    def create_action(self, user, actiontype, data, validdays):
        action = self.model(user=user, atype=actiontype, data=data)
        action.validuntil = timezone.now() + timedelta(validdays)
        action.code = md5(user.username +
                          ACTION_TYPES[actiontype] +
                          data +
                          action.validuntil.strftime(
                              "%Y%m%d%H%M%S%f")).hexdigest()
        action.save(using=self.db)
        return action


class Action(models.Model):
    """
    Action model.

    """
    user = models.ForeignKey('User')
    code = models.CharField(_('action code'), max_length=32, unique=True)
    created = AutoCreatedField(_('created'))
    validuntil = models.DateTimeField(_('valid until'), db_index=True)
    atype = models.PositiveSmallIntegerField(_('action type'),
                                             choices=ACTION_TYPES,
                                             db_index=True)
    data = models.TextField(_('action data'))

    objects = ActionManager()

    class Meta:
        ordering = ['-validuntil']

    def __unicode__(self):
        return "%s valid until %s" % (ACTION_TYPES[self.atype],
                                      self.validuntil)
