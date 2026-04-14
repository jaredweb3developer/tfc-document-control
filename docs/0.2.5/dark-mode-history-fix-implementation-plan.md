# 0.2.5 Dark Mode History Fix Implementation Plan

## Goal

Fix the `Source` files history-status highlight so highlighted filenames remain readable in dark mode without changing the existing meaning of the highlight colors.

## Problem Summary

- The source files table applies light custom background colors for history states.
- In dark mode, Qt can keep a light custom background while still rendering the text with a theme-provided light foreground.
- This produces white-on-light text for highlighted filenames, which is hard to read.

## Chosen Fix

- Keep the current highlight background colors for:
  - checked out by you
  - checked out by another user
  - has document history
- When applying one of those highlights, also apply an explicit dark foreground color to the same item.
- Leave non-highlighted rows unchanged so the native theme still controls normal table text.

## Scope

- Update the source-file history highlight helper in `document_control/mixins/records.py`.
- Add a targeted regression test covering highlighted foreground color assignment.
- Record the user-visible behavior adjustment in repository docs.

## Acceptance Criteria

- In dark mode, highlighted source-file names remain readable when the history highlight is applied.
- Light mode behavior remains visually consistent with the current status colors.
- Non-highlighted source-file rows continue using the platform/theme default foreground.
