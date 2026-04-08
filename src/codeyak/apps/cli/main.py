"""
CLI for CodeYak - Local and MR code review.

Usage:
    yak review              # Review local uncommitted changes
    yak mr <MR_ID> [PROJECT_ID]  # Review GitLab MR
"""

import click

from ... import __version__
from .commands import review, mr, learn, summary, install_skill


@click.group()
@click.version_option(version=__version__, prog_name="yak")
def main():
    """CodeYak - AI-powered code review tool."""
    pass


main.add_command(review)
main.add_command(mr)
main.add_command(learn)
main.add_command(summary)
main.add_command(install_skill)


if __name__ == "__main__":
    main()
