#!/usr/bin/env python

# Copyright (c) 2016, Anodized Software, Inc.
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
# 1. Redistributions of source code must retain the above copyright notice,
# this list of conditions and the following disclaimer.
#
# 2. Redistributions in binary form must reproduce the above copyright notice,
# this list of conditions and the following disclaimer in the documentation
# and/or other materials provided with the distribution.
#
# 3. Neither the name of the copyright holder nor the names of its
# contributors may be used to endorse or promote products derived from this
# software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE
# LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
# CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
# SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
# INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
# CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
# ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.

import argparse
import codecs
from subprocess import call, CalledProcessError, check_call, check_output, Popen, PIPE
import sys

###############################################################################
## CONFIGURATION

# Path to git binary
GIT = "/usr/local/bin/git"

# Path to avgtool binary
AGVTOOL = "/usr/bin/agvtool"

# Path to PlistBuddy binary
PLIST_BUDDY = "/usr/libexec/PlistBuddy"

# Path to the Root.plist file in the app's Settings.bundle
#
# If set, the script will use PlistBuddy to set the version number in the plist
# file so the app's version number appears in the Settings app.
#
# If set to None, this step is skipped with a warning printed.
#
# For example:
# SETTINGS_PLIST = "path/to/Settings.bundle/Root.plist"
SETTINGS_PLIST = None

###############################################################################
## VERSION NUMBERING (AGVTOOL)

def get_marketing_version():
    return check_output([AGVTOOL, "what-marketing-version", "-terse1"]).strip()

def set_marketing_version(version, verbose=False):
    output = check_output([AGVTOOL, "new-marketing-version", version])

    if verbose:
        print output.strip()

def get_build_number():
    return check_output([AGVTOOL, "what-version", "-terse"]).strip()

def set_build_number(build_number, verbose=False):
    output = check_output([AGVTOOL, "new-version", "-all", build_number])

    if verbose:
        print output.strip()

def bump_build_number(verbose=False):
    output = check_output([AGVTOOL, "bump", "-all"])

    if verbose:
        print output.strip()

def get_formatted_version():
    marketing_version = get_marketing_version()
    build_number = get_build_number()
    return "%s_%s" % (marketing_version, build_number)

###############################################################################
## SETTINGS PLIST VERSION

def set_version_in_settings_plist(plist_filename, version=None):
    if version is None:
        version = get_formatted_version()

    print "Setting version to", version, "in", plist_filename
    check_call([PLIST_BUDDY, plist_filename, "-c", "set PreferenceSpecifiers:1:DefaultValue %s" % version])

###############################################################################
## GIT

# See http://stackoverflow.com/a/3879077/511287
def is_work_tree_clean(msg):
    is_error = False

    # update the index
    check_call([GIT, "update-index", "-q", "--ignore-submodules", "--refresh"])

    # disallow unstaged changes in the working tree
    if call([GIT, "diff-files", "--quiet", "--ignore-submodules", "--"]) != 0:
        print >>sys.stderr, "Cannot %s: there are unstaged changes" % msg

        output = check_output([GIT, "diff-files", "--name-status", "-r", "--ignore-submodules", "--"])
        print >>sys.stderr, output.strip()

        is_error = True

    # disallow uncommitted changes in the index
    if call([GIT, "diff-index", "--cached", "--quiet", "HEAD", "--ignore-submodules", "--"]) != 0:
        print >>sys.stderr, "Cannot %s: the index contains uncommitted changes" % msg

        output = check_output([GIT, "diff-index", "--cached", "--name-status", "-r", "--ignore-submodules", "HEAD", "--"])
        print >>sys.stderr, output.strip()

        is_error = True

    if is_error:
        print >>sys.stderr, "Please commit or stash them"
        return False

    else:
        return True

def git_add(filename):
    check_call([GIT, "add", filename])

def git_commit_current_version():
    message = "Automated build of %s" % get_formatted_version()
    check_call([GIT, "commit", "--all", "--message=%s" % message])

def git_tag_current_version():
    version = get_formatted_version()
    tag_name = "releases/v%s" % version
    message = "Automated tagging of version %s" % version
    check_call([GIT, "tag", "--annotate", tag_name, "--message=%s" % message])
    return tag_name

def git_push_tag(tag_name):
    check_call([GIT, "push", "origin", tag_name])

def log_as_release_notes(from_tag, to_tag="HEAD"):
    output = check_output([GIT, "log", "--reverse", '--pretty=format:* `%h` %s', "%s..%s" % (from_tag, to_tag)])
    return output.strip()

###############################################################################
## BUMP BUILD NUMBER AND GENERATE RELEASE NOTES

def pbcopy(value):
    process = Popen("pbcopy", env={"LANG": "en_US.UTF-8"}, stdin=PIPE)
    process.communicate(value.encode())

def make_build(prev_tag):
    if not is_work_tree_clean("start"):
        return 1

    bump_build_number()
    print "Version changed to %s" % get_formatted_version()

    if SETTINGS_PLIST is None:
        print >>sys.stderr, "The SETTINGS_PLIST variable is not set. Skipping."
    else:
        set_version_in_settings_plist(SETTINGS_PLIST)
        print "Updated settings plist"

    release_notes_filename = "ReleaseNotes/v%s.mkd" % get_formatted_version()
    release_notes = log_as_release_notes(prev_tag)

    with codecs.open(release_notes_filename, "w", "utf-8") as fh:
        print >>fh, release_notes

    pbcopy(release_notes)
    print release_notes_filename, "generated and copied to pasteboard"

    git_add(release_notes_filename)
    git_commit_current_version()
    git_tag_current_version()

###############################################################################
## COMMAND-LINE INTERFACE

def previous_tag():
    try:
        return "releases/v%s" % get_formatted_version()
    except CalledProcessError:
        return None

def parse_args(argv):
    if argv is None:
        argv = sys.argv[1:]

    parser = argparse.ArgumentParser(description="")

    subparsers = parser.add_subparsers()

    get_marketing_version = subparsers.add_parser("get-marketing-version", help="prints the marketing version")
    get_marketing_version.set_defaults(subcommand="get-marketing-version")

    set_marketing_version = subparsers.add_parser("set-marketing-version", help="sets the marketing version")
    set_marketing_version.set_defaults(subcommand="set-marketing-version")
    set_marketing_version.add_argument("-v", "--verbose",
                                       default=False,
                                       action="store_true",
                                       help="print verbose output")
    set_marketing_version.add_argument("version", help="the new marketing version")

    get_build_number = subparsers.add_parser("get-build-number", help="prints the build number")
    get_build_number.set_defaults(subcommand="get-build-number")

    set_build_number = subparsers.add_parser("set-build-number", help="sets the build number")
    set_build_number.set_defaults(subcommand="set-build-number")
    set_build_number.add_argument("-v", "--verbose",
                                  default=False,
                                  action="store_true",
                                  help="print verbose output")
    set_build_number.add_argument("version", help="the new build number")

    get_full_version = subparsers.add_parser("get-full-version", help="prints the formatted version number")
    get_full_version.set_defaults(subcommand="get-full-version")

    make_build = subparsers.add_parser("make-build", help="bumps the build number and generates release notes")
    make_build.set_defaults(subcommand="make-build")
    make_build.add_argument("--prev-tag", "-p",
                            default=previous_tag(),
                            help="previous tag (for release notes)")

    return parser.parse_args(argv)

def main(argv=None):
    options = parse_args(argv)

    if options.subcommand == "get-marketing-version":
        print get_marketing_version()

    elif options.subcommand == "set-marketing-version":
        set_marketing_version(options.version, options.verbose)

    elif options.subcommand == "get-build-number":
        print get_build_number()

    elif options.subcommand == "set-build-number":
        set_build_number(options.version, options.verbose)

    elif options.subcommand == "get-full-version":
        print get_formatted_version()

    elif options.subcommand == "make-build":
        make_build(options.prev_tag)

    else:
        raise Exception("Unknown subcommand: %s" % options.subcommand)

if __name__ == "__main__":
    sys.exit(main())

