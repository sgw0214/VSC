# Web MVP Wireframe and Components

## Screen 1: Today

```
+-------------------------------------------------+
| English Line Drill                    [Install] |
| Total 20 | Due 20 | Reviewed 0                 |
+-------------------------------------------------+
| [Today] [Practice] [Review]                    |
+-------------------------------------------------+
| Today's 5 Lines                      [Shuffle] |
| - 1. Ordering Coffee (A2 | Cafe)              |
| - 8. Restaurant Reservation (A2 | Restaurant) |
| - 3. Rescheduling a Meeting (B1 | Office)     |
| - 14. Asking for a Discount (B1 | Market)     |
| - 20. Networking Introduction (B1 | Event)    |
+-------------------------------------------------+
```

## Screen 2: Practice

```
+-------------------------------------------------+
| [Today] [Practice*] [Review]                   |
+-------------------------------------------------+
| Dialogue Practice                              |
| 3. Rescheduling a Meeting | B1 | Office        |
| [Can we move ...] [Something came up] [...]    |
| 1) A: Can we move our meeting to tomorrow?     |
| 2) B: Sure. Did something come up?             |
| 3) A: Yes, I need more time...                 |
| 4) B: No problem. Does 10 a.m. work for you?   |
| [Play] [Show KO] [Cloze]                       |
| Cloze: Can we move our ______ to tomorrow?     |
| [Prev]               3 / 20              [Next]|
+-------------------------------------------------+
```

## Screen 3: Review

```
+-------------------------------------------------+
| [Today] [Practice] [Review*]                   |
+-------------------------------------------------+
| Review Queue                         [Refresh] |
| - 2. Asking for Directions  Due: 2026-03-30    |
| - 5. Returning an Item     Due: 2026-03-30     |
| - 11. Online Meeting Issue Due: 2026-03-30     |
| Recall sentence:                               |
| [___________________________________________]   |
| Score: [0] [1] [2] [3] [4] [5]                 |
| Guide: 5 exact -> 0 blank                       |
+-------------------------------------------------+
```

## Component List

- `Topbar`: app title, install button
- `StatGrid`: total dialogues, due today, reviewed today
- `Tabbar`: Today/Practice/Review screen switch
- `TodayList`: daily line set shortlist
- `DialogueCard`: title, patterns, turns, playback, cloze
- `Pager`: previous/next dialogue controls
- `ReviewQueue`: due items with repetition metadata
- `RecallInput`: free typing for active recall
- `ScoreButtons`: SRS feedback (0 to 5)

## Data Contract

- `GET /api/dialogues`: list of dialogue sets
- `GET /api/review/next`: due queue for SRS
- `POST /api/review/attempt`: store score and update due date
- `GET /api/stats`: counters for dashboard cards
