# -*- coding: utf-8 -*-
from __future__ import unicode_literals
import re
import datetime
import random

from pytimeparse.timeparse import timeparse

import calendar_events
import strings
import util


class RSVPMessage(object):
  """Class that represents a response from an RSVPCommand.

  Every call to an RSVPCommand instance's execute() method is expected to return an instance
  of this class.
  """
  def __init__(self, msg_type, body, to=None, subject=None):
    self.type = msg_type
    self.body = body
    self.to = to
    self.subject = subject

  def __getitem__(self, attr):
    self.__dict__[attr]

  def __str__(self):
    attr_string = ""
    for key in dir(self):
      attr_string += key + ":" + str(getattr(self, key)) + ", "
    return attr_string


class RSVPCommandResponse(object):
  def __init__(self, events, *args):
    self.events = events
    self.messages = []
    for arg in args:
      if isinstance(arg, RSVPMessage):
        self.messages.append(arg)


class RSVPCommand(object):
  """Base class for an RSVPCommand."""
  regex = None

  def __init__(self, prefix, *args, **kwargs):
    # prefix is the command start the bot listens to, typically 'rsvp'
    self.prefix = r'^' + prefix + r' '
    self.regex = self.prefix + self.regex

  def match(self, input_str):
    return re.match(self.regex, input_str, flags=re.DOTALL | re.I)

  def execute(self, events, *args, **kwargs):
    """execute() is just a convenience wrapper around __run()."""
    return self.run(events, *args, **kwargs)


class RSVPEventNeededCommand(RSVPCommand):
  """Base class for a command where an event needs to exist prior to execution."""
  def execute(self, events, *args, **kwargs):
    event = kwargs.get('event')
    if event:
      return self.run(events, *args, **kwargs)
    return RSVPCommandResponse(events, RSVPMessage('stream', strings.ERROR_NOT_AN_EVENT))


class RSVPInitCommand(RSVPCommand):
  regex = r'init$'

  def run(self, events, *args, **kwargs):
    sender_id   = kwargs.pop('sender_id')
    event_id    = kwargs.pop('event_id')
    subject    = kwargs.pop('subject')

    body = strings.MSG_INIT_SUCCESSFUL

    if events.get(event_id):
      # Event already exists, error message, we can't initialize twice.
      body = strings.ERROR_ALREADY_AN_EVENT
    else:
      # Update the dictionary with the new event and commit.
      events.update(
        {
          event_id: {
            'name': subject,
            'description': None,
            'place': None,
            'creator': sender_id,
            'yes': [],
            'no': [],
            'maybe': [],
            'time': None,
            'limit': None,
            'date': '%s' % datetime.date.today(),
            'calendar_event': None,
            'duration': None,
          }
        }
      )

    response = RSVPCommandResponse(events, RSVPMessage('stream', body))
    return response


class RSVPSetDurationCommand(RSVPEventNeededCommand):
  regex = r'set duration (?P<duration>.+)$'

  def run(self, events, *args, **kwargs):
    event = kwargs.pop('event')
    event_id = kwargs.pop('event_id')
    duration = kwargs.pop('duration')

    parsed_duration_in_seconds = timeparse(duration, granularity='minutes')
    event['duration'] = parsed_duration_in_seconds
    body = strings.MSG_DURATION_SET % datetime.timedelta(seconds=parsed_duration_in_seconds)
    calendar_event_id = event.get('calendar_event') and event['calendar_event']['id']
    if calendar_event_id:
      try:
        calendar_events.update_gcal_event(event, event_id)
      except calendar_events.KeyfilePathNotSpecifiedError:
        pass

    return RSVPCommandResponse(events, RSVPMessage('stream', body))


class RSVPCreateCalendarEventCommand(RSVPEventNeededCommand):
  regex = r'add to calendar$'

  def run(self, events, *args, **kwargs):
    event = kwargs.pop('event')
    event_id = kwargs.pop('event_id')

    try:
      cal_event = calendar_events.add_rsvpbot_event_to_gcal(event, event_id)
    except calendar_events.KeyfilePathNotSpecifiedError:
      body = strings.ERROR_CALENDAR_ENVS_NOT_SET
    except calendar_events.DateAndTimeNotSuppliedError:
      body = strings.ERROR_DATE_AND_TIME_NOT_SET
    except calendar_events.DurationNotSuppliedError:
      body = strings.ERROR_DURATION_NOT_SET
    else:
      event['calendar_event'] = {}
      event['calendar_event']['id'] = cal_event.get('id')
      event['calendar_event']['html_link'] = cal_event.get('htmlLink')
      body = strings.MSG_ADDED_TO_CALENDAR.format(
          calendar_name=cal_event.get('calendar_name'),
          url=cal_event.get('htmlLink'))

    return RSVPCommandResponse(events, RSVPMessage('stream', body))


class RSVPQuickInitCommand(RSVPCommand):
  regex = r'quickinit (?P<date>.*)\|(?P<time>.*)\|(?P<duration>.*)\|(?P<location>.*)\|(?P<description>.*)'

  def run(self, events, *args, **kwargs):
    sender_id   = kwargs.pop('sender_id')
    event_id    = kwargs.pop('event_id')
    subject    = kwargs.pop('subject')
    date    = kwargs.pop('date')
    time    = kwargs.pop('time')
    duration    = kwargs.pop('duration')
    location    = kwargs.pop('location')
    description    = kwargs.pop('description')

    body = strings.MSG_INIT_SUCCESSFUL

    if events.get(event_id):
      # Event already exists, error message, we can't initialize twice.
      body = strings.ERROR_ALREADY_AN_EVENT
    else:
      # Update the dictionary with the new event and commit.
      events.update(
        {
          event_id: {
            'name': subject,
            'description': description,
            'place': location,
            'creator': sender_id,
            'yes': [],
            'no': [],
            'maybe': [],
            'time': time,
            'limit': None,
            'date': date,
          }
        }
      )

    response = RSVPCommandResponse(events, RSVPMessage('stream', body))
    return response


class RSVPHelpCommand(RSVPCommand):
  regex = r'help$'

  def run(self, events, *args, **kwargs):
    body = "**Command**|**Description**\n"
    body += "--- | ---\n"
    body += "**`rsvp yes`**|Marks **you** as attending this event.\n"
    body += "**`rsvp no`**|Marks you as **not** attending this event.\n"
    body += "`rsvp init`|Initializes a thread as an RSVPBot event. Must be used before any other command.\n"
    body += "`rsvp help`|Shows this handy table.\n"
    body += "`rsvp ping <message>`|Pings everyone that has RSVP'd so far. Optionally, sends a message, if provided.\n"
    body += "`rsvp set time HH:mm`|Sets the time for this event (24-hour format) (optional)\n"
    body += "`rsvp set date mm/dd/yyyy`|Sets the date for this event (optional, if not explicitly set, the date for the event is the date of the creation of the event, i.e. the call to `rsvp init`)\n"
    body += "`rsvp set duration HH:mm or 30m`|Sets the length of time this event will last (optional, only required for adding the event to the Calendar).\n"
    body += "`rsvp add to calendar`|Creates an event on the Calendar. Requires time, date, and duration to be set first.\n"
    body += "`rsvp set description DESCRIPTION`|Sets this event's description to DESCRIPTION (optional)\n"
    body += "`rsvp set place PLACE_NAME`|Sets the place for this event to PLACE_NAME (optional)\n"
    body += "`rsvp set limit LIMIT`|Set the attendance limit for this event to LIMIT. Set LIMIT as 0 for infinite attendees.\n"
    body += "`rsvp cancel`|Cancels this event (can only be called by the caller of `rsvp init`)\n"
    body += "`rsvp move <destination_url>`|Moves this event to another stream/topic. Requires full URL for the destination (e.g.'https://zulip.com/#narrow/stream/announce/topic/All.20Hands.20Meeting') (can only be called by the caller of `rsvp init`)\n"
    body += "`rsvp summary`|Displays a summary of this event, including the description, and list of attendees.\n"
    body += "`rsvp credits`|Lists all the awesome people that made RSVPBot a reality.\n"

    return RSVPCommandResponse(events, RSVPMessage('private', body))


class RSVPCancelCommand(RSVPEventNeededCommand):
  regex = r'cancel$'

  def run(self, events, *args, **kwargs):
    event_id = kwargs.pop('event_id')
    sender_id = kwargs.pop('sender_id')
    event = kwargs.pop('event')

    # Check if the issuer of this command is the event's original creator.
    # Only they can delete the event.
    creator = event['creator']

    if creator == sender_id:
      body = strings.MSG_EVENT_CANCELED
      events.pop(event_id)
    else:
      body = strings.ERROR_NOT_AUTHORIZED_TO_DELETE

    return RSVPCommandResponse(events, RSVPMessage('stream', body))


class RSVPMoveCommand(RSVPEventNeededCommand):
  regex = r'move (?P<destination>.+)$'

  def run(self, events, *args, **kwargs):
    event_id = kwargs.pop('event_id')
    sender_id = kwargs.pop('sender_id')
    event = kwargs.pop('event')
    destination = kwargs.pop('destination')
    success_msg = None

    # Check if the issuer of this command is the event's original creator.
    # Only she can modify the event.
    creator = event['creator']

    # check and make sure a valid Zulip stream/topic URL is passed
    if not destination: 
      body = strings.ERROR_MISSING_MOVE_DESTINATION
    elif creator != sender_id:
      body = strings.ERROR_NOT_AUTHORIZED_TO_DELETE
    else:
      # split URL into components
      stream, topic = util.narrow_url_to_stream_topic(destination)

      if stream is None or topic is None:
        body = strings.ERROR_BAD_MOVE_DESTINATION % destination
      else:
        new_event_id = stream + "/" + topic

        if new_event_id in events:
          body = strings.ERROR_MOVE_ALREADY_AN_EVENT % new_event_id
        else:
          body = strings.MSG_EVENT_MOVED % (new_event_id, destination)

          old_event = events.pop(event_id)

          # need to make sure that there's no duplicate here!
          # also, ideally we'd make sure the stream/topic existed & create it if not.
          # AND send an 'init' notification to that new stream/toipic. Hm. what's the
          # best way to do that? Allow for a parameterized init? It's always a reply, not a push.
          # Can we return MULTIPLE messages instead of just one?

          old_event.update({'name': topic})

          events.update(
            {
              new_event_id: old_event
            }
          )

          success_msg = RSVPMessage('stream', strings.MSG_INIT_SUCCESSFUL, stream, topic)

    return RSVPCommandResponse(events, RSVPMessage('stream', body), success_msg)


class LimitReachedException(Exception):
  pass


class RSVPConfirmCommand(RSVPEventNeededCommand):
  regex = r'.*?\b(?P<decision>(yes|no|maybe))\b'

  responses = {
    "yes": '@**%s** is attending!',
    "no": '@**%s** is **not** attending!',
    "maybe": '@**%s** might be attending. It\'s complicated.',
  }

  vips = []
  with open('vips.txt', 'r') as vips_file:
    vips = [vip_name.strip() for vip_name in vips_file]

  vip_yes_prefixes = [
    "GET EXCITED!! ",
    "AWWW YISS!! ",
    "YASSSSS HENNY! ",
    "OMG OMG OMG ",
    "HYPE HYPE HYPE HYPE HYPE ",
    "WOW THIS IS AWESOME: ",
    "YEAAAAAAHHH!!!! :tada: ",
  ]

  vip_no_postfixes = [
    " :confounded:",
    " Bummer!",
    " Oh no!!",
  ]

  def confirm(self, event, event_id, sender_email, decision):
    # Temporary kludge to add a 'maybe' array to legacy events. Can be removed after
    # all currently logged events have passed.
    if ('maybe' not in event.keys()):
      event['maybe'] = []

    # If they're in a different response list, take them out of it.
    for response in self.responses.keys():
      # prevent duplicates if replying multiple times
      if (response == decision):
        # if they're already in that list, nothing to do
        if (sender_email not in event[response]):
          event[response].append(sender_email)
      # else, remove all instances of them from other response lists.
      elif sender_email in event[response]:
        event[response] = [value for value in event[response] if value != sender_email]
      calendar_event_id = event.get('calendar_event') and event['calendar_event']['id']
      if calendar_event_id:
        try:
          calendar_events.update_gcal_event(event, event_id)
        except calendar_events.KeyfilePathNotSpecifiedError:
          pass

    return event

  def attempt_confirm(self, event, event_id, sender_email, decision, limit):
    if decision == 'yes' and limit:
      available_seats = limit - len(event['yes'])
      # In this case, we need to do some extra checking for the attendance limit.
      if (available_seats - 1 < 0):
        raise LimitReachedException()

    return self.confirm(event, event_id, sender_email, decision)

  def run(self, events, *args, **kwargs):
    event_id = kwargs.pop('event_id')
    event = kwargs.pop('event')
    decision = kwargs.pop('decision').lower()
    sender_full_name = kwargs.pop('sender_full_name')
    sender_email = kwargs.pop('sender_email')

    limit = event['limit']

    vip_prefix = ''
    vip_postfix = ''

    # TODO:
    # if (this.yes_no_ambigous()):
    #   return RSVPCommandResponse("Yes no yes_no_ambigous", events)

    try:
      event = self.attempt_confirm(event, event_id,  sender_email, decision, limit)

      if sender_full_name in self.vips:
        if decision == 'yes':
          vip_prefix = random.choice(self.vip_yes_prefixes)
        else:
          vip_postfix = random.choice(self.vip_no_postfixes)

      # Update the events dict with the new event.
      events[event_id] = event
      response_string = self.responses.get(decision) % sender_full_name
      response_string = vip_prefix + response_string + vip_postfix
      return RSVPCommandResponse(events, RSVPMessage('stream', response_string))

    except LimitReachedException:
      return RSVPCommandResponse(events, RSVPMessage('stream', strings.ERROR_LIMIT_REACHED))


class RSVPSetLimitCommand(RSVPEventNeededCommand):
  regex = r'set limit (?P<limit>\d+)$'

  def run(self, events, *args, **kwargs):

    event = kwargs.pop('event')
    attendance_limit = int(kwargs.pop('limit'))
    event['limit'] = attendance_limit
    return RSVPCommandResponse(events, RSVPMessage('stream', strings.MSG_ATTENDANCE_LIMIT_SET % attendance_limit))


class RSVPSetDateCommand(RSVPEventNeededCommand):
  regex = r'set date (?P<month>\d{1,2})/(?P<day>\d{1,2})/(?P<year>\d{4})$'

  def validate_future_date(self, day, month, year):
    today = datetime.date.today()

    try:
      date = datetime.date(year, month, day)
    except ValueError:
      return False

    return date >= today

  def run(self, events, *args, **kwargs):
    event = kwargs.pop('event')
    event_id = kwargs.pop('event_id')
    day = kwargs.pop('day')
    month = kwargs.pop('month')
    year = kwargs.pop('year')

    day, month, year = int(day), int(month), int(year)

    if self.validate_future_date(day, month, year):
      event['date'] = str(datetime.date(year, month, day))
      events[event_id] = event
      body = strings.MSG_DATE_SET % (month, day, year)
      calendar_event_id = event.get('calendar_event') and event['calendar_event']['id']
      if calendar_event_id:
        try:
          calendar_events.update_gcal_event(event, event_id)
        except calendar_events.KeyfilePathNotSpecifiedError:
          pass
    else:
      body = strings.ERROR_DATE_NOT_VALID % (month, day, year)

    return RSVPCommandResponse(events, RSVPMessage('stream', body))


class RSVPSetTimeCommand(RSVPEventNeededCommand):
  regex = r'set time (?P<hours>\d{1,2})\:(?P<minutes>\d{1,2})$'

  def run(self, events, *args, **kwargs):
    event_id = kwargs.pop('event_id')
    hours, minutes = int(kwargs.pop('hours')), int(kwargs.pop('minutes'))

    if hours in range(0, 24) and minutes in range(0, 60):
      event = events[event_id]
      event['time'] = '%02d:%02d' % (hours, minutes)
      body = strings.MSG_TIME_SET % (hours, minutes)
      calendar_event_id = event.get('calendar_event') and event['calendar_event']['id']
      if calendar_event_id:
        try:
          calendar_events.update_gcal_event(event, event_id)
        except calendar_events.KeyfilePathNotSpecifiedError:
          pass
    else:
      body = strings.ERROR_TIME_NOT_VALID % (hours, minutes)

    return RSVPCommandResponse(events, RSVPMessage('stream', body))


class RSVPSetTimeAllDayCommand(RSVPEventNeededCommand):
  regex = r'set time allday$'

  def run(self, events, *args, **kwargs):
    event_id = kwargs.pop('event_id')
    events[event_id]['time'] = None
    return RSVPCommandResponse(events, RSVPMessage('stream', strings.MSG_TIME_SET_ALLDAY))


class RSVPSetStringAttributeCommand(RSVPEventNeededCommand):
  regex = r'set (?P<attribute>(place|description)) (?P<value>.+)$'

  def run(self, events, *args, **kwargs):
    event_id = kwargs.pop('event_id')
    attribute = kwargs.pop('attribute')
    value = kwargs.pop('value')

    event = events[event_id]
    event[attribute] = value
    calendar_event_id = event.get('calendar_event') and event['calendar_event']['id']
    if calendar_event_id:
      try:
        calendar_events.update_gcal_event(event, event_id)
      except calendar_events.KeyfilePathNotSpecifiedError:
        pass
    body = strings.MSG_STRING_ATTR_SET % (attribute, value)
    return RSVPCommandResponse(events, RSVPMessage('stream', body))


def get_all_users_from_zulip_client(zulip_client=None):
    all_users = None
    if zulip_client:
        users_result = zulip_client.get_users()
        if users_result['result'] == 'success':
            all_users = users_result['members']
    return all_users


class RSVPPingCommand(RSVPEventNeededCommand):
  regex = r'^({key_word} ping)$|({key_word} ping (?P<message>.+))$'

  def __init__(self, prefix, *args, **kwargs):
    self.regex = self.regex.format(key_word=prefix)

  def run(self, events, *args, **kwargs):
    zulip_client = args[0]

    event = kwargs.pop('event')
    message = kwargs.get('message')

    body = "**Pinging all participants who RSVP'd!!**\n"

    all_users = get_all_users_from_zulip_client(zulip_client)

    for participant in event['yes']:
      body += "@**%s** " % convert_name_or_email_to_pingable_name(all_users, participant)

    for participant in event['maybe']:
      body += "@**%s** " % convert_name_or_email_to_pingable_name(all_users, participant)

    if message:
      body += ('\n' + message)

    return RSVPCommandResponse(events, RSVPMessage('stream', body))


def convert_name_or_email_to_pingable_name(all_users, name_or_email):
  if all_users:
    for user in all_users:
      if user['email'] == name_or_email:
        return user['full_name']
  return name_or_email


class RSVPCreditsCommand(RSVPEventNeededCommand):
  regex = r'credits$'

  def run(self, events, *args, **kwargs):

    contributors = [
      "Mudit Ameta (SP2'15)",
      "Diego Berrocal (F2'15)",
      "Shad William Hopson (F1'15)",
      "Tom Murphy (F2'15)",
      "Miriam Shiffman (F2'15)",
      "Anjana Sofia Vakil (F2'15)",
      "Steven McCarthy (SP2'15)",
      "Kara McNair (F2'15)",
      "Pris Nasrat (SP2'16)",
      "Benjamin Gilbert (F2'15)",
      "Andrew Drozdov (SP1'15)",
      "Alex Wilson (S1'16)",
    ]

    testers = ["Nikki Bee (SP2'15)", "Anthony Burdi (SP1'15)", "Noella D'sa (SP2'15)", "Mudit Ameta (SP2'15)"]

    body = "The RSVPBot was created by @**Carlos Rey (SP2'15)**\nWith **contributions** from:\n\n"

    body += '\n '.join(contributors)

    body += "\n\n and invaluable test feedback from:\n\n"
    body += '\n '.join(testers)

    body += "\n\nThe code for **RSVPBot** is available at https://github.com/kokeshii/RSVPBot"

    return RSVPCommandResponse(events, RSVPMessage('stream', body))


class RSVPSummaryCommand(RSVPEventNeededCommand):
  regex = r'(summary$|status$)'

  def run(self, events, *args, **kwargs):
    event = kwargs.pop('event')
    zulip_client = args[0]

    limit_str = 'No Limit!'

    if event['limit']:
      limit_str = '%d/%d spots left' % (event['limit'] - len(event['yes']), event['limit'])

    summary_table = '**%s**' % (event['name'])
    summary_table += '\t|\t\n:---:|:---:\n**What**|%s\n**When**|%s @ %s\n**Where**|%s\n**Limit**|%s\n'
    summary_table = summary_table % (
      event['description'] or 'N/A',
      event['date'],
      event['time'] or '(All day)',
      event['place'] or 'N/A',
      limit_str
    )

    confirmation_table = 'YES ({}) |NO ({}) |MAYBE({}) \n:---:|:---:|:---:\n'

    confirmation_table = confirmation_table.format(len(event['yes']), len(event['no']), len(event['maybe']))

    all_users = get_all_users_from_zulip_client(zulip_client)

    row_list = map(None, event['yes'], event['no'], event['maybe'])

    for row in row_list:
      confirmation_table += '{}|{}|{}\n'.format(
        '' if row[0] is None else convert_name_or_email_to_pingable_name(all_users, row[0]),
        '' if row[1] is None else convert_name_or_email_to_pingable_name(all_users, row[1]),
        '' if row[2] is None else convert_name_or_email_to_pingable_name(all_users, row[2])
      )
    else:
      confirmation_table += '\t|\t'

    body = summary_table + '\n\n' + confirmation_table
    return RSVPCommandResponse(events, RSVPMessage('stream', body))
