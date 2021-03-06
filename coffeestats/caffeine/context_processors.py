# -*- coding: utf-8 -*-
from django.core.urlresolvers import reverse
from django.utils.translation import ugettext as _


class NavItem(object):
    def __init__(self, request, url, title, css_class):
        self.url = url
        self.title = title
        self.active = request.path == url
        self.css_class = css_class

    def is_active(self):
        return self.active


class SubNavItem(object):
    def __init__(self, request, url, title, css_class="subNavLink"):
        self.url = url
        self.title = title
        self.css_class = css_class


class SubNav(object):
    def __init__(
        self, request, title, css_class, children, children_css_class
    ):
        self.title = title
        self.css_class = css_class
        self.children = children
        self.active = any(
            [request.path == child.url for child in children]
        )
        self.children_css_class = children_css_class

    def is_active(self):
        return self.active


def mainnav(request):
    retval = {}
    if request.user.is_authenticated():
        navitems = [
            NavItem(request, reverse('profile'),
                    _('Profile'), 'navprofile'),
            NavItem(request, reverse('explore'),
                    _('Explore'), 'navexplore'),
            NavItem(request, reverse('overall'),
                    _('Overall Stats'), 'navoverall'),
        ]

        if request.user.is_staff:
            settingschildren = [
                SubNavItem(request, reverse('admin:index'),
                           _('Admin site')),
            ]
        else:
            settingschildren = []
        settingschildren.extend([
            SubNavItem(request, reverse('about'),
                       _('About')),
            SubNavItem(request, reverse('settings'),
                       _('Settings')),
            SubNavItem(request, reverse('auth_logout'),
                       _('Logout'), 'btn'),
        ])

        settingsnav = SubNav(request, _('Settings'),
                             'settings', settingschildren,
                             'settingsBox')
        navitems.append(settingsnav)
        retval['navitems'] = navitems
    return retval
