# Numbered dish positions — 26 November 2026

Saving Display order inserts a dish at that position, shifting its peers and
compacting the list to 1, 2, 3. Moving down closes the old gap; a number beyond
the list length means the end. Legacy zero is accepted as first position.
Breakfast, Lunch, Dinner and Shop have independent position maps. Shared dishes
keep their other meal positions. Daily availability and stock do not change
positions; hidden and unavailable dishes retain their library positions.

The display_positions JSON field is additive. Existing sort/priority values
provide the fallback until an explicit save normalizes the store's libraries.
Position updates and dish/date edits commit together under a store lock; a later
validation failure rolls back all shifts. Old invoices and stock are untouched.

Validation includes PostgreSQL regression tests for insertion, moving both ways,
independent shared-meal positions, tenant isolation and rollback, plus actual
browser edits in both versions verifying shifted input numbers and customer order.
