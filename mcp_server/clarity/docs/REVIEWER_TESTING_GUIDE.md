# Clarity — Reviewer Testing Guide

## Installation

1. Add Clarity app from directory
2. No separate login required. Reviewer installs the app and can use tools immediately.

## Test Flow

### 1. Create Board
Type in chat:
> "I have a lot on my mind: finish report, call dentist, plan vacation, buy groceries, exercise more"

**Expected**: Widget renders with thoughts grouped into clusters.

### 2. Prioritize
Type in chat:
> "Make 'finish report' my P1"

**Expected**: P1 badge appears on the relevant cluster/item.

### 3. Save Board
Type in chat:
> "Save my board"

**Expected**: Transient "Saved" confirmation appears in widget header.

### 4. Load Saved Board (New Conversation)
Start a new conversation. Type:
> "Show my saved board"

**Expected**: Previously saved board loads with all clusters and priorities intact.

### 5. Edit Board
Type in chat:
> "Add 'send invoice' to Work cluster"

**Expected**: New thought item appears in the specified cluster.

### 6. Delete Data
Type in chat:
> "Delete all my Clarity data"

Then confirm when prompted.

**Expected**: All data deleted. Confirmation message displayed.

## Keyboard Navigation

1. Press Tab to move through clusters
2. Each cluster card should receive visible focus ring
3. Focus should not get stuck

## Modal Behavior

1. Click Save button in widget header
2. Modal opens, focus on Cancel button
3. Tab cycles between Cancel and Save only
4. Press Escape — modal closes, focus returns to Save button
