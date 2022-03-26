import argparse
import json
import pathlib
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Set
from functools import singledispatch

import apprise
import requests
import time

from hungryAPI import HungryAPI
from shift import Shift
from timeslot import RecurringTimeslot
from Storage import Storage

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Checks if there are shifts available on hungry.dk',
                                     epilog='Good luck in your shift search! :)')
    parser.add_argument("email", help="Your hungry.dk email", type=str)
    parser.add_argument("password", help="Your hungry.dk password", type=str)
    parser.add_argument("id", help="Your hungry.dk employee ID (see app -> my profile)", type=int)
    parser.add_argument("notify", help="Apprise notification URL")
    parser.add_argument("--auto-take", help="Automatically take shifts that the chosen timeslots", action="store_true",
                        default=False)
    parser.add_argument("-d", "--debug", help="Enable debug mode", action="store_true")
    parser.add_argument("-f", "--frequency", help="Executes the script every <seconds> (use CRON instead!)",
                        metavar="seconds", type=int)
    args = parser.parse_args()

    # set up logging
    if args.debug:
        import logging
        logging.basicConfig(level=logging.DEBUG)

    # Notifications
    appriseObj = apprise.Apprise()
    if appriseObj.add(args.notify) is False:
        raise Exception("The given Apprise notification URL is invalid. ")

    # Hungry
    hungry = HungryAPI(args.email, args.password, args.id)

    # Storage
    storage = Storage()

    # Load timeslots from storage
    if len(storage.recurring_timeslots) == 0:
        print("No timeslots found. Creating a default one")
        # Create a recurring timeslot that covers all days of week, all hours, and all shift lengths
        # days of week
        days_of_week = [0, 1, 2, 3, 4, 5, 6]
        # start and end time
        start = datetime.strptime("00:00", "%H:%M")
        end = datetime.strptime("23:59", "%H:%M")
        # min shift length (minutes)
        shift_length = 0
        # create a recurring timeslot
        timeslot = RecurringTimeslot(days_of_week, start.time(), end.time(), shift_length)

        # add the timeslot to the storage
        storage.add_recurring_timeslot(timeslot)

    # Run once or every args.frequency seconds
    print("Starting the script...")
    while True:
        # Get shifts
        shifts = hungry.get_shifts()

        # Read saved shifts from storage
        saved_shifts = storage.get_shifts()

        # Find shifts that are not saved
        new_shifts = [shift for shift in shifts if shift not in saved_shifts]

        # Save shifts to storage
        storage.save_shifts(shifts)

        # Get shifts that satisfy the user specified timeslots
        valid_shifts = set()
        for timeslot in storage.recurring_timeslots:
            for shift in new_shifts:
                if timeslot.is_valid_shift(shift.start, shift.end):
                    valid_shifts.add(shift)

        # Take shifts
        if args.auto_take:
            for shift in valid_shifts:
                print(f"Taking shift {shift.start} - {shift.end}")

                # Take the shift
                hungry.take_shift(shift)

        # Notify if a valid shift is found
        if len(valid_shifts) > 0:
            # print that shifts were found or taken depending on the auto-take flag
            if args.auto_take:
                print(f"{len(valid_shifts)} shifts were taken.")
            else:
                print(f"{len(valid_shifts)} shifts were found.")
            shifts_repr: str = '\n'.join(str(s) for s in shifts)
            print(shifts_repr)
            appriseObj.notify(body=shifts_repr, title=f"{len(shifts)} new shifts found!")
        if args.frequency is None:
            break
        time.sleep(args.frequency)
    print("Done!")
