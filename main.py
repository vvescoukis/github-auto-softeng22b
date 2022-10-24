#!/usr/bin/env python3

import argparse
import pandas
import subprocess

from github import Github, GithubException

import config

INSTRUCTORS = ["nickie", "vvescoukis", "TzannetosGiannis", "ChristosHadjichristofi"]

def confirm(question, default="no"):
    """Ask a yes/no question and return the answer.

    "question" is a string that is presented to the user.
    "default" is the presumed answer if the user just hits <Enter>.
        It must be "yes" (the default), "no" or None (meaning
        an answer is required of the user).

    The "answer" return value is True for "yes" or False for "no".
    """
    valid = {"yes": True, "y": True, "ye": True, "no": False, "n": False}
    if default is None:    prompt = "y/n"
    elif default == "yes": prompt = "Y/n"
    elif default == "no":  prompt = "y/N"
    else: raise ValueError("invalid default answer: '{}'".format(default))
    while True:
        print("{}  [{}]: ".format(question, prompt), end="")
        choice = input().lower()
        if default is not None and choice == "": return valid[default]
        elif choice in valid: return valid[choice]
        else: print("Please respond with 'yes' or 'no'")

""" update softengNN, TLNN each year... """
def valid_team_id(team):
    PREFIX = "SoftEng22-"
    if pandas.isnull(team):
        return None, "team field empty"
    if not (team.startswith(PREFIX) and team[len(PREFIX):].isdigit()):
        return None, "invalid team '{}'".format(team)
    return "SoftEng22-{:02d}".format(int(team[len(PREFIX):])), None

def valid_github_username(username):
    if not isinstance(username, str):
        return False
    if not len(username.split()) == 1:
        return False
    if not 4 <= len(username) <= 39:
        return False
    return True

def invalid_row(row):
    if pandas.isnull(row.email) or not row.email:
        return "email probably empty"
    if not isinstance(row.email, str):
        return "email is not valid"
    if pandas.isnull(row.team) or not row.team:
        return "team name probably empty"
    if not isinstance(row.team, str):
        return "team is not valid"
    if pandas.isnull(row.id) or not row.id:
        return "NTUA ID probably empty"
    if pandas.isnull(row.lastname) or not row.lastname:
        return "lastname probably empty"
    if pandas.isnull(row.firstname) or not row.firstname:
        return "firstname probably empty"
    if pandas.isnull(row.username) or not row.username:
        return "username probably empty"
    if not valid_github_username(row.username):
        return "username is not valid"

def parse_team_info(verbose=True):
    def info(*args, **kwargs):
        if verbose:
            print(*args, **kwargs)
    info("Parsing the teams")
    x = pandas.ExcelFile(config.xlsxfile)
    df = x.parse(config.xlsxsheet)
    df.rename(inplace=True, columns={
        'Email address': 'email',
        'Group': 'team',
        'ID number': 'id',
        'Surname': 'lastname',
        'First name': 'firstname',
        'github user name': 'username',
    })
    df.fillna({'username': '<null>'}, inplace=True)
    seen = {}
    teams = {}
    for i, row in enumerate(df.itertuples(index=False, name="User"), 2):
        # If row is duplicate, print it and skip it
        if not pandas.isnull(row.id):
            # print(row)
            id = row.id.strip()
            if id in seen:
                info("Skipping line {}: {} was already seen in line {}".format(
                    i, id, seen[id]))
                continue
            seen[id] = i
        else:
            info("Skipping line {}: no NTUA identity".format(i))

        # Acquire team information before fully checking member.
        # This is required in order to mark team as 'not good' when
        # performing full checks.
        team_id, err = valid_team_id(row.team)
        if team_id is not None:
            if team_id not in teams:
                teams[team_id] = { 'name': row.team, 'members': [] }
            teams[team_id]['members'].append(row)
        elif not pandas.isnull(row.id):
            info("Skipping line {}: {} for {}".format(i, err, row.id))

    # Teams validation
    for team_id in sorted(teams):
        good = True
        # If team size is invalid, skip it
        # modified to accept teams of 1 (2021)
        if not 1 <= len(teams[team_id]['members']) <= 6:
            info("Team {} ({}) has {} member(s), skipping team".format(
                team_id, teams[team_id]['name'],
                len(teams[team_id]['members'])))
            good = False
        # Check members for errors
        for row in teams[team_id]['members']:
            # Row validation
            err = invalid_row(row)
            # If an error was returned, print it and skip team
            if err is not None:
                if good:
                    info("Team {} ({}) has member errors:".format(
                        team_id, teams[team_id]['name']))
                good = False
                info("  Invalid member information: '{} {} <{}>'".format(
                    row.lastname, row.firstname, row.email))
                info("    ERROR: {}".format(err))
        teams[team_id]['good'] = good
    return teams

def print_team(id, name, members):
    print("Team {}: {}".format(id, name))
    for row in members:
        print("  {} {} <{}> {}".format(
            row.firstname, row.lastname, row.email, row.username))

def print_team_csv(id, name, members):      # added on 2021 by vv for convenience
    # print("{}: {}".format(id, name))
    for row in members:
        print("{}; {}; {}; {}; {}; {}".format(
            id, name, row.username, row.email, row.lastname, row.firstname))

def print_teams(teams):
    for team_id in sorted(teams):
        print()
        print_team(team_id, teams[team_id]['name'], teams[team_id]['members'])

def print_teams_csv(teams):                 # added on 2021 by vv for convenience
    print()
    print("teamID; teamName; username; email; lastname; firstname")
    for team_id in sorted(teams):
        # print()
        print_team_csv(team_id, teams[team_id]['name'], teams[team_id]['members'])


class GithubOrganizationManager:
    def __init__(self, token, organization, team=None, template=None,
                 action='confirm', verbose=True, only_members=False):
        self.action = action
        self.verbose = verbose
        self.only_members = only_members
        self.g = Github(token)
        self.info("Successfully logged in to GitHub")
        self.user = self.g.get_user()
        self.info("User: {id} or {login} --- {name} <{email}>".format(
            id=self.user.id, login=self.user.login,
            name=self.user.name, email=self.user.email))
        self.organization = self.g.get_organization(organization)
        self.info("Organization: {id} or {login} --- {name}".format(
            id=self.organization.id, login=self.organization.login,
            name=self.organization.name))
        if team:
            print(team)
            self.team = self.organization.get_team_by_slug(team)
            self.info("Team: {id} or {name}".format(
                id=self.team.id, name=self.team.name))
        self.template = template

    def info(self, *args, **kwargs):
        if self.verbose:
            print(*args, **kwargs)

    def warn(self, *args, **kwargs):
        print(*args, **kwargs)

    def add_member_to_org(self, user):
        if self.action:
            role = "owner" if user.login in INSTRUCTORS else "member"
            self.organization.add_to_members(user, role=role)

    def create_team(self, id, name, members):
        print_team(id, name, members)
        if self.action == 'confirm' and not confirm("Create?"): return
        self.info()
        self.info("Creating repository for team {}: {}".format(id, name))
        # Create a private repos.
        repos_created = False
        if self.action:
            try:
                repos = self.organization.create_repo(id, private=True)
                repos_created = True
                self.info("  Done.")
            except:
                self.info("  Repos {} already exists.".format(id))
                repos = self.organization.get_repo(id)
        else:
            try:
                repos = self.organization.get_repo(id)
                self.info("  Repos {} already exists.".format(id))
            except:
                self.warn("  Repos {} does not exist, aborting!".format(id))
                return
        # Add the administrator team.
        if self.team and not self.team.has_in_repos(repos):
            if self.action:
                self.team.add_to_repos(repos)
                self.team.update_team_repository(repos, "admin")
            self.info("  Added administrator team.")
        # Add the team members.
        # grep-friendly faillure messages by vv on 27 dec 2021
        for row in members:
            self.info("  {} {} <{}> {}".format(
                row.firstname, row.lastname, row.email, row.username))
            try:
                user = self.g.get_user(row.username)
            except GithubException:
                self.warn("  [ATTENTION] GitHub user {} not found for team with id={}!".format(
                    row.username, id))
                continue
            if not self.organization.has_in_members(user):
                self.add_member_to_org(user)
                self.info("  [ATTENTION] User {} is invited to join organization {} (team={})".format(
                    user.login, self.organization.login, id))
            elif not repos.has_in_collaborators(user):
                if self.action:
                    repos.add_to_collaborators(user, permission="push")
                self.info("  User {} added".format(user.login))
        # Initialize the repository
        if self.only_members or not self.template: return
        def with_template(cmd):
            try:
                self.info("  {}".format(cmd))
                if not self.action: return
                cp = subprocess.run(cmd, cwd=self.template, shell=True)
                if cp.returncode < 0:
                    self.warn("  terminated by signal", -cp.returncode)
                elif cp.returncode > 0:
                    self.warn("  returned", cp.returncode)
            except OSError as e:
                self.warn("  execution failed:", e)
        with_template("git remote add {} {}".format(id, repos.ssh_url))
        with_template("git push {} main".format(id))
        with_template("git remote rm {}".format(id))
        # We should apply some protection to the master branch here.
        # Not yet fully supported by PyGithub, if I understand it right.
        """
        master = repos.get_branch("main")
        master.edit_protection(strict=True, ...)
        """

if __name__ == "__main__":
    import sys
    # Command line options.
    parser = argparse.ArgumentParser(description="GitHub Automation Tool.")
    group = parser.add_mutually_exclusive_group()
    group.add_argument('-n', '--dry-run', action='store_false',
                       dest="action", default='confirm',
                       help="do not take any real action with GitHub")
    parser.add_argument('-t', '--teams', action='store_true',
                        dest="just_teams", default=False,
                        help="just parse and print the teams")
    parser.add_argument('-c', '--csv', action='store_true',             # added on 2021 by vv for convenience
                        dest="just_teams_csv", default=False,
                        help="just parse and print the teams as csv-friendly")
    group.add_argument('-y', '--yes', action='store_true',
                       dest="action", default='confirm',
                       help="assume 'yes' to all confirmation questions")
    parser.add_argument('-q', '--quiet', action='store_false',
                        dest="verbose", default=True,
                        help="silence informational messages (default: no)")
    parser.add_argument('-m', '--members', action='store_true',
                        dest="members", default=False,
                        help="only update team members")
    parser.add_argument('teams', metavar='teams', type=str, nargs='*',
                        help="specify which teams to work with (default: all)")
    args = parser.parse_args()

    # Parse the file with team information.
    teams = parse_team_info(verbose=args.verbose)

    # Display team data
    if args.just_teams:
        print_teams(teams)
        sys.exit(0)
    if args.just_teams_csv:
        print_teams_csv(teams)
        sys.exit(0)

    # Talk to GitHub and do the rest.
    manager = GithubOrganizationManager(config.token, config.organization,
                                        config.team, config.template,
                                        action=args.action,
                                        only_members=args.members,
                                        verbose=args.verbose)
    for key in args.teams or sorted(teams):
        print()
        manager.create_team(key, teams[key]['name'], teams[key]['members'])
