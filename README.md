# WaterLineage Gauteng (v2.4 Verified)

Elevation-aware municipal water outage map and reticulation lineage tracker for Greater Gauteng (Johannesburg, Midrand, Sandton, Randburg, Roodepoort, Soweto, Tshwane, Ekurhuleni, and Mogale City).

## What Was Fixed in v2.4
1. **No Fake Clock Overrides**: Replaced the synthetic time-of-day reservoir percentage simulator with verified November 2026 Johannesburg Water & City of Johannesburg reservoir statuses (`Grand Central` tower suspended / 14%, `Erand` 35% outlet open, `President Park` 67%, `Brixton 1` 91% / `Brixton 2` 50%, `Hursthill 2` bypassed 22%, `Honeydew` 16%, `Morningside/Sandton` 37% bypass, `Crown Gardens` 100%).
2. **Real Interactive Outage Map (Leaflet.js)**: Full interactive Gauteng map showing all 17 reservoir supply zones, clickable suburb elevation markers, and toggleable emergency water tanker standpipe locations.
3. **Dedicated Address Focus Mode**: Searching any street or clicking a preset/map pin automatically hides the provincial overview grid and focuses 100% on that street's 4-tier upstream lineage, 30m NASA SRTM ground elevation, complex backup tank buffer simulator, and 2D Hydraulic Grade Line (HGL) cross-section.
4. **Fixed Relative Suburb Percentile + Static Head Physics**: Eliminates the hardcoded 70m delta bug by calculating each street's topographic percentile within its local supply zone (`(street_elev - zone_floor) / (zone_crest - zone_floor)`) alongside live effective hydraulic head.
5. **Ad-Free Civic Utility Interface**: Removed all ad banners, R39/mo SMS paywalls, and commercial clutter.
