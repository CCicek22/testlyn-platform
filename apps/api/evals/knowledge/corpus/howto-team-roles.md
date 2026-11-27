# How to manage team roles

Brackwater has four project roles. Each one is a set of permissions, and you
assign them per project rather than per organization.

## The roles

The `viewer` role reads runs, reports and targets. It cannot start a run.

The `runner` role does everything a viewer can do and also starts and stops
runs. Most engineers need this role.

The `editor` role adds the ability to create and change targets, scenarios and
profiles. Give it to the owner of a service, not to every member.

The `admin` role manages members, roles and API keys. Each project should have
at least two admins so that one departure does not lock the project.

## Inviting a teammate

Open the project settings, choose Members, then Invite. Enter the work email
address and pick a role. The invitation expires after seven days. An expired
invitation can be sent again without creating a new one.

Invitations to an address outside the organization domain need an admin of the
organization to approve them. The approval appears in the audit log.

## Removing access

Removing a member revokes their sessions immediately. It does not delete their
runs or reports, because those belong to the project. API keys created by the
member keep working until an admin revokes them, so check the key list after
every removal.

## Service accounts

Automation should use a service account with the `runner` role rather than a
personal login. Service accounts cannot sign in to the web console, and their
API keys expire after 90 days unless renewed.

## Audit

Every role change is written to the audit log with the actor, the target user,
the old role and the new role. The log is kept for 400 days and can be exported
as CSV from the organization settings.
