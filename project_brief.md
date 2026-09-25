# My agent: bayfly
One-liner: A conversational agent that helps Bay Area travelers compare and choose flights across SJC, SFO, and OAK as equal options, dynamically tailored for business vs. leisure travel.

Tool coverage:
- Memory: Trip context preference (business vs. leisure), home city/ZIP (for transit estimates), airline loyalty, baggage needs.
- Tools: Multi-airport flight comparison search (evaluating SJC, SFO, and OAK side-by-side), travel mode evaluator (business: non-stop/low delay risk/schedule; leisure: price/baggage/group value), airport transit/parking cost calculator.
- Catalog/UI: Side-by-side comparison tables/cards showing options from all 3 airports with "Best for Business" vs "Best Value" highlights.
- Image gen: Destination preview or postcard image.
- Sandbox: Door-to-door cost & travel time calculator (airfare + parking/transit + drive time).

Recommended for every project: memory, storage, tools, image generation, A2UI
Agent-specific / stretch (pick what fits): code sandbox for total-cost/time trade-off calculations, external flight or transit lookup APIs, Cloud Trace.
