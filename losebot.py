#!/usr/bin/env python

import datetime
import sys
import mechanize
import os
import getpass
import configparser

# Program for downloading and parsing log data from the Loseit.com web site.


# Compute time range for weekly food log files that we want to download.
# We go BACKWARDS in time from "now".
# Start is a Monday 8am for most recent week with FULL data--in other words, skip this current week.
# Endpoint is where we left off last time -- initially  May 10, 2010 (start of all data)
EXPORT_WEEKLY_DATA_URL = "https://loseit.com/export/weekly?date=%s"
SETTINGS_URL = "https://www.loseit.com/#Settings:Subscription%5ESubscription"
WEEK_SECS = 604800  # 1 week in seconds
DOWNLOAD_DIR = os.path.dirname(os.path.abspath(__file__)) + "/downloaded_loseit_food_exercise/"
LOSE_IT_CREATION_DATE = datetime.datetime.strptime("2008-01-01", '%Y-%m-%d')

# todo another app: load into mysql for analysis?

def main():
    start_date = ""
    user = ""
    password = ""
    br = mechanize.Browser()
    br.set_handle_robots(False)
    br.addheaders = [
        ('User-agent', 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.10; rv:57.0) Gecko/20100101 Firefox/57.0')]
    if len(sys.argv) > 1:
        if not os.path.exists(sys.argv[1]):
            print("cannot find file: %s" % sys.argv[1])
            sys.exit(1)
        config = configparser.RawConfigParser()
        config.read(sys.argv[1])
        try:
            user = config.get('Losebot', 'username')
            password = config.get('Losebot', 'password')
            start_date = config.get('Losebot', 'startdate')
        except Exception:
            print("""
Expected file to have a header and 3 required entries like:

[Losebot]
username=myemail@someserver.com
password=mysecretpassword
startdate=2018-05-01
""")
            sys.exit(1)

    if user == "" or password == "":
        password, user = prompt_login()

    login(br, "https://loseit.com/account/", user, password)

    if not is_logged_in(br):
        print("login unsuccessful")
        sys.exit(1)

    # first case: check download dir to see what we have already, if any
    last_downloaded_timestamp = get_most_recently_download_timestamp()
    if last_downloaded_timestamp == 0:
        # user's first time; use start date from file or prompt for start date
        if start_date is "":
            start_date_timestamp = prompt_start_date()
        else:
            start_date_timestamp = convert_datetime_to_timestamp(start_date)

    else:
        # if start_date and last_downloaded are both specified
        # warn & use last download
        if start_date is not "":
            print("Overriding specified start date because we found previous downloads; updating from there.")
        start_date_timestamp = last_downloaded_timestamp

    download_weekly_food_log_files(br, start_date_timestamp)
    merge_downloaded_files()


def convert_datetime_to_timestamp(year_month_day_string):
    start_date_parsed = datetime.datetime.strptime(year_month_day_string, '%Y-%m-%d')
    start_date_timestamp = float(start_date_parsed.strftime("%s"))
    return start_date_timestamp


def prompt_login():
    user = input("Username: ")
    password = getpass.getpass("Password: ")
    return password, user


def login(br, url, user, password):
    print("attempting to log in...")
    br.open(url)
    br.select_form(id="loginForm")
    br.form["username"] = user
    br.form["password"] = password
    br.submit()


def pretty_date(secs_since_epoch):
    value = datetime.datetime.fromtimestamp(secs_since_epoch)
    return value.strftime('%Y-%m-%d')


def content_is_ok(filename):
    with open(filename) as f:
        return "Date,Name,Icon,Type,Quantity,Units,Calories,Deleted,Fat" in f.readline()


def download_weekly_food_log_files(br, start_date_timestamp):
    weekly_timestamp = get_starting_week_timestamp()
    if weekly_timestamp <= start_date_timestamp:
        print("nothing to download: up to date")
        sys.exit(0)

    # iterate backwards from last week until we hit the start_date
    while weekly_timestamp > start_date_timestamp:
        filename = DOWNLOAD_DIR + "%s_food.csv" % pretty_date(weekly_timestamp)
        url_timestamp_millis = int(round(weekly_timestamp * 1000))
        br.retrieve(EXPORT_WEEKLY_DATA_URL % url_timestamp_millis, filename)
        if not content_is_ok(filename):
            os.remove(filename)
            print("failed to retrieve " + EXPORT_WEEKLY_DATA_URL % url_timestamp_millis)
            sys.exit(1)
        else:
            print("saved file: %s" % filename)
            weekly_timestamp -= WEEK_SECS


def is_logged_in(br):
    # a redirect to a page with a login means that you have NOT successfully logged in.
    # a page with a login has "Sign In" in text.
    page_contents = br.response().read()
    return "Sign In" not in str(page_contents)


def get_starting_week_timestamp():
    # start point is the Monday a week-plus ago, at 8am GMT -- to get full week of data
    today = datetime.datetime.now()

    # Go back to Monday before last Monday by subtracting off the days of this week plus another week
    last_monday = today + datetime.timedelta(days=-today.weekday() - 7)
    last_monday = last_monday.replace(hour=8, minute=0, second=0)
    return float(last_monday.strftime("%s"))


def get_most_recently_download_timestamp():
    if not os.path.exists(DOWNLOAD_DIR):
        os.makedirs(DOWNLOAD_DIR)
    all_files = os.listdir(DOWNLOAD_DIR)
    if len(all_files) == 0:
        return 0
    in_order = sorted(all_files)
    most_recent_file = in_order[-1]
    most_recent_date = datetime.datetime.strptime(most_recent_file, '%Y-%m-%d_food.csv')
    most_recent_date = most_recent_date.replace(hour=8, minute=0, second=0)
    return float(most_recent_date.strftime("%s"))


def get_start_date(br):
    br.open(SETTINGS_URL)
    text = br.response().read()
    print(text)


def prompt_start_date():
    one_year_ago = datetime.datetime.now() - datetime.timedelta(days=365)
    pretty_one_year_ago = pretty_date(float(one_year_ago.strftime("%s")))
    start_str = input(
        "Start date, in format YYYY-MM-DD, defaults to %s: " % pretty_one_year_ago) or pretty_one_year_ago
    # if start date is prior to when LoseIt began, use LoseIt creation date Jan 2008
    print("start date is: %s" % start_str)
    try:
        start_date = datetime.datetime.strptime(start_str, '%Y-%m-%d')
        if start_date < LOSE_IT_CREATION_DATE:
            print("Your date is before LoseIt started collecting data in 2008, so using start date of January 2008")
            start_date = LOSE_IT_CREATION_DATE
    except:
        print("Bad format for start date: '%s'; using default of a year ago" % start_str)
        start_date = one_year_ago
    return float(start_date.strftime("%s"))


def merge_downloaded_files():
    csv_files = os.listdir(DOWNLOAD_DIR)
    file_name = 'merged.csv'
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), file_name), 'w') as out_file:
        is_first_file = True
        for csv_file in csv_files:
            if csv_file.endswith('_food.csv'):
                with open(os.path.join(DOWNLOAD_DIR, csv_file), 'r') as in_file:
                    lines = in_file.read().split('\n')
                    first_line = 0 if is_first_file else 1
                    is_first_file = False
                    for line in lines[first_line:]:
                        if len(line) > 0:
                            out_file.write(f'{line}\n')


main()
