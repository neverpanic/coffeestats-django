import os

from django.core import mail
from django.test import TestCase
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password

from registration.models import RegistrationProfile

from caffeine.forms import (
    CoffeestatsRegistrationForm,
)
from caffeine.views import (
    ACTIVATION_SUCCESS_MESSAGE,
    DELETE_ACCOUNT_MESSAGE,
    EXPORT_SUCCESS_MESSAGE,
    REGISTRATION_MAILINFO_MESSAGE,
    REGISTRATION_SUCCESS_MESSAGE,
)


User = get_user_model()
os.environ['RECAPTCHA_TESTING'] = 'True'

HASHED_DEFAULT_PASSWORD = make_password('test1234')


class CaffeineViewTest(TestCase):

    def _create_testuser(self):
        user = User.objects.create(
            username='testuser', email='test@bla.com',
            password=HASHED_DEFAULT_PASSWORD, token='testfoo'
        )
        user.timezone = 'Europe/Berlin'
        user.save()
        return user

    def _do_login(self):
        self._create_testuser()
        return self.client.login(username='testuser', password='test1234')


class MessagesTestMixin(object):

    def assertMessageCount(self, response, expected_num):
        self.assertEqual(len(response.context['messages']),
                         expected_num)

    def assertMessageContains(self, response, text, level=None):
        response_messages = response.context['messages']
        matches = [m for m in response_messages if text in m.message]

        if len(matches) == 1:
            msg = matches[0]
            if level is not None and msg.level != level:
                self.fail('There was one matching message but different'
                          ' level: %s != %s' % (msg.level, level))
        elif len(matches) == 0:
            messages_str = ', '.join('"%s"' % m for m in response_messages)
            self.fail('No message contained text "%s", messages were: %s' %
                      (text, messages_str))
        else:
            self.fail('Multiple messages contained text "%s": %s' %
                      (text, ', '.join(('"%s"' % m) for m in matches)))


class AboutViewTest(CaffeineViewTest):

    def test_redirects_to_login(self):
        response = self.client.get('/about/')
        self.assertRedirects(
            response, '/auth/login/?next=/about/')

    def test_renders_about_template(self):
        self.assertTrue(self._do_login(), 'login failed')
        response = self.client.get('/about/')
        self.assertTemplateUsed(response, 'about.html')


class ExploreViewTest(CaffeineViewTest):

    def test_redirects_to_login(self):
        response = self.client.get('/explore/')
        self.assertRedirects(
            response, '/auth/login/?next=/explore/')

    def test_renders_explore_template(self):
        self.assertTrue(self._do_login(), 'login failed')
        response = self.client.get('/explore/')
        self.assertTemplateUsed(response, 'explore.html')

    def test_context_items(self):
        self.assertTrue(self._do_login(), 'login failed')
        response = self.client.get('/explore/')
        for item in ('activities', 'users', 'topcoffee',
                     'topcoffeeavg', 'topmate', 'topmateavg',
                     'recentlyjoined', 'longestjoined'):
            self.assertIn(item, response.context)


class ExportActivityView(MessagesTestMixin, CaffeineViewTest):

    def test_redirects_to_login(self):
        response = self.client.get('/activity/export/')
        self.assertRedirects(
            response, '/auth/login/?next=/activity/export/')

    def test_sends_csv_mail(self):
        self.assertTrue(self._do_login(), 'login failed')
        response = self.client.get('/activity/export/', follow=True)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].subject, 'Your caffeine records')
        self.assertMessageCount(response, 1)
        self.assertMessageContains(
            response, EXPORT_SUCCESS_MESSAGE, messages.INFO)


class DeleteAccountViewTest(MessagesTestMixin, CaffeineViewTest):

    def test_redirects_to_login(self):
        response = self.client.get('/deletemyaccount/')
        self.assertRedirects(
            response, '/auth/login/?next=/deletemyaccount/')

    def test_renders_delete_confirmation_template(self):
        self.assertTrue(self._do_login(), 'login failed')
        response = self.client.get('/deletemyaccount/')
        self.assertTemplateUsed(response, 'caffeine/user_confirm_delete.html')
        self.assertIn('user', response.context)

    def test_delete(self):
        self.assertTrue(self._do_login(), 'login failed')
        response = self.client.post('/deletemyaccount/', follow=True)
        self.assertMessageCount(response, 1)
        self.assertMessageContains(
            response, DELETE_ACCOUNT_MESSAGE, messages.INFO)
        self.assertFalse(self.client.login(
            username='testuser', password='test1234'))


class ImprintViewTest(TestCase):

    def test_renders_imprint_template(self):
        response = self.client.get('/imprint/')
        self.assertTemplateUsed(response, 'imprint.html')


class IndexViewTest(CaffeineViewTest):

    def test_redirects_to_login(self):
        response = self.client.get('/')
        self.assertRedirects(
            response, '/auth/login/?next=/')

    def test_renders_index_template(self):
        self.assertTrue(self._do_login(), 'login failed')
        response = self.client.get('/')
        self.assertTemplateUsed(response, 'index.html')


class OverallViewTest(CaffeineViewTest):

    def test_redirects_to_login(self):
        response = self.client.get('/overall/')
        self.assertRedirects(
            response, '/auth/login/?next=/overall/')

    def test_renders_overall_template(self):
        self.assertTrue(self._do_login(), 'login failed')
        response = self.client.get('/overall/')
        self.assertTemplateUsed(response, 'overall.html')

    def test_context_items(self):
        self.assertTrue(self._do_login(), 'login failed')
        response = self.client.get('/overall/')
        for item in ('coffees', 'mate', 'todaydata', 'monthdata', 'yeardata',
                     'byhourdata', 'byweekdaydata'):
            self.assertIn(item, response.context)


class ProfileViewsTest(CaffeineViewTest):
    """
    Test case for both ProfileView and PublicProfileView.

    """

    def test_bad_request_for_anonymous(self):
        response = self.client.get('/profile/')
        self.assertEqual(response.status_code, 400)

    def test_notfound_for_missing_user(self):
        response = self.client.get('/profile/testuser/')
        self.assertEqual(response.status_code, 404)

    def test_redirects_to_public_for_parameter(self):
        self._create_testuser()
        response = self.client.get('/profile/?u=testuser')
        self.assertRedirects(response, '/profile/testuser/')

    def test_renders_profile_template_for_ownprofile(self):
        self.assertTrue(self._do_login(), 'login failed')
        response = self.client.get('/profile/')
        self.assertTemplateUsed(response, 'profile.html')

    def test_renders_profile_template_for_parameter(self):
        self._create_testuser()
        response = self.client.get('/profile/testuser/')
        self.assertTemplateUsed(response, 'profile.html')

    def test_context_items_public(self):
        self._create_testuser()
        response = self.client.get('/profile/testuser/')
        for item in ('byhourdata', 'byweekdaydata', 'coffees', 'mate',
                     'monthdata', 'ownprofile', 'profileuser', 'todaydata',
                     'yeardata'):
            self.assertIn(item, response.context)
        self.assertNotIn('entries', response.context)
        self.assertFalse(response.context['ownprofile'])

    def test_context_items_own(self):
        self.assertTrue(self._do_login(), 'login failed')
        response = self.client.get('/profile/')
        for item in ('byhourdata', 'byweekdaydata', 'coffees', 'mate',
                     'monthdata', 'ownprofile', 'profileuser', 'todaydata',
                     'yeardata', 'entries'):
            self.assertIn(item, response.context)
        self.assertTrue(response.context['ownprofile'])


class CaffeineActivationViewTest(MessagesTestMixin, CaffeineViewTest):

    def test_redirects_to_home(self):
        user = self._create_testuser()
        regprofile = RegistrationProfile.objects.create_profile(user)
        response = self.client.get('/auth/activate/{}/'.format(
            regprofile.activation_key), follow=True)
        self.assertRedirects(response, '/auth/login/?next=/')

    def test_activation_success_message(self):
        user = self._create_testuser()
        regprofile = RegistrationProfile.objects.create_profile(user)
        response = self.client.get('/auth/activate/{}/'.format(
            regprofile.activation_key), follow=True)
        self.assertMessageCount(response, 1)
        self.assertMessageContains(response, ACTIVATION_SUCCESS_MESSAGE)


class CaffeineRegistrationViewTest(MessagesTestMixin, CaffeineViewTest):

    TEST_POST_DATA = {
        'username': 'testuser',
        'email': 'test@bla.com',
        'password1': 'test1234',
        'password2': 'test1234',
        'firstname': 'Test',
        'lastname': 'User',
        'location': 'Testino',
        'recaptcha_response_field': 'PASSED'
    }

    def test_get_renders_registration_template(self):
        response = self.client.get('/auth/register/')
        self.assertTemplateUsed(
            response, 'registration/registration_form.html')

    def test_get_context_has_form(self):
        response = self.client.get('/auth/register/')
        self.assertIn('form', response.context)
        self.assertIsInstance(
            response.context['form'], CoffeestatsRegistrationForm)

    def test_empty_post_renders_errors(self):
        response = self.client.post('/auth/register/', data={})
        self.assertIn('errorlist', response.content)

    def test_successful_post_creates_inactive_user(self):
        self.client.post('/auth/register/', data=self.TEST_POST_DATA)
        user = User.objects.get(username=self.TEST_POST_DATA['username'])
        self.assertFalse(user.is_active)
        self.assertEqual(user.first_name, self.TEST_POST_DATA['firstname'])
        self.assertEqual(user.last_name, self.TEST_POST_DATA['lastname'])
        self.assertEqual(user.location, self.TEST_POST_DATA['location'])

    def test_successful_post_creates_registration_profile(self):
        self.client.post('/auth/register/', data=self.TEST_POST_DATA)
        self.assertEqual(len(RegistrationProfile.objects.all()), 1)

    def test_successful_post_sends_email(self):
        self.client.post('/auth/register/', data=self.TEST_POST_DATA)
        regprofile = RegistrationProfile.objects.all()[0]
        self.assertEqual(len(mail.outbox), 1)
        firstmail = mail.outbox[0]
        self.assertEquals(firstmail.to, [self.TEST_POST_DATA['email']])
        self.assertIn(regprofile.activation_key, firstmail.body)

    def test_successful_post_creates_messages(self):
        response = self.client.post(
            '/auth/register/', data=self.TEST_POST_DATA, follow=True)
        self.assertMessageCount(response, 2)
        self.assertMessageContains(
            response, REGISTRATION_SUCCESS_MESSAGE, messages.SUCCESS)
        self.assertMessageContains(
            response, REGISTRATION_MAILINFO_MESSAGE, messages.INFO)

    def test_redirects_to_home(self):
        response = self.client.post(
            '/auth/register/', data=self.TEST_POST_DATA, follow=True)
        self.assertRedirects(response, '/auth/login/?next=/')
