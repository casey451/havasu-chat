# resend_eightlotus_week2.ps1 — post the 6 two-week-consistent Eight Lotus findings
# at confidence 0.85 (week-1 2026-06-04 + week-2 2026-06-11 observations).
#
# *** DO NOT RUN until the auto-publish gate is verified. ***
# On 2026-06-11 POST /api/ingest/contribution auto-PUBLISHED instead of queueing
# (11 records incl. a 0.50-conf one — see scratch/SCHEDULE_HUNT_NOTES.md and
# docs/scraper/reports/schedule_hunt_2026-06-11.md). At 0.85 these would go LIVE
# instantly if the gate is still broken/on. Check SCHEDULE_HUNT_AUTOPUBLISH +
# THRESHOLD in Railway first.
#
# EXPECTED RESULT once run: most/all of these should return status=duplicate
# (pending contributions 563/564/612-616 share the same normalized titles), in
# which case the confidence raise needs the manual review path in
# /admin/contributions instead. The titles below intentionally match the
# originals so you can pair them.
#
# Usage:  .\scripts\resend_eightlotus_week2.ps1            # posts
#         .\scripts\resend_eightlotus_week2.ps1 -WhatIf    # prints payload summary, posts nothing
# (PowerShell 5.1 compatible; reads INGEST_API_TOKEN from .env, never prints it)
param([switch]$WhatIf)
$ErrorActionPreference = "Stop"
# NOTE 2026-06-11: havasu-chat-production.up.railway.app now 308-redirects to
# askhava.com and POST bodies don't survive the redirect — post to askhava.com.
$base = "https://askhava.com"
# $base = "https://havasu-chat-production.up.railway.app"   # old base, 308s

$line = (Get-Content .env | Where-Object { $_ -match '^INGEST_API_TOKEN=' } | Select-Object -First 1)
if (-not $line) { Write-Host "FAIL: no INGEST_API_TOKEN in .env"; exit 1 }
$tok = $line.Split('=',2)[1].Trim().Trim('"').Trim("'")

$eid = "35fcab51-bf9a-4cf9-ac98-816ce54d95d9"
$src = "https://www.8lotuswellness.com/book-class"
$ven = "Eight Lotus Center for Wellness"
$cost = "`$20 walk-in; `$100/mo unlimited; `$150 10-class"
$obs = "Two-week consistent observation (live Mindbody booking feed read 6/4/26 and 6/11/26) - supersedes the earlier single-week finding."

$payloads = @(
    @{  # pairs with pending contribution 563
        entity_type = "program"; submission_name = $ven; source_url = $src
        confidence = 0.85; target_entity_id = $eid
        proposed_record = @{
            title = "TruFusion Pilates"
            description = "Dynamic Pilates fusion class building core strength, flexibility and mind-body balance. 60 min. Held Monday and Friday 8:15am in both observed weeks. $obs Week of 6/11 ALSO showed a Wednesday 8:15am session and a Tuesday early-morning session (5:30am on 6/9) - single-week extras, not included here."
            schedule_days = @("monday","friday")
            schedule_start_time = "08:15"; schedule_end_time = "09:15"
            location_name = $ven; provider_name = $ven; cost = $cost
            contact_phone = "928-208-7477"; contact_url = $src
            tags = @("pilates","fitness")
        }
    },
    @{  # pairs with pending contribution 564
        entity_type = "program"; submission_name = $ven; source_url = $src
        confidence = 0.85; target_entity_id = $eid
        proposed_record = @{
            title = "Belly Dance"
            description = "Belly dance class with Savanna Cosentino combining technique and follow-along cardio. Two back-to-back Monday sessions in both observed weeks: 6:15pm (beginners) and 7:15pm (choreography); this record carries the 6:15pm session. Week of 6/11 the Mindbody feed titles them 'Belly Dance: Beginners' and 'Belly Dance: Choreography'. $obs"
            schedule_days = @("monday")
            schedule_start_time = "18:15"; schedule_end_time = "19:15"
            location_name = $ven; provider_name = $ven; cost = $cost
            contact_phone = "928-208-7477"; contact_url = $src
            tags = @("dance","fitness")
        }
    },
    @{  # pairs with pending contribution 612
        entity_type = "program"; submission_name = $ven; source_url = $src
        confidence = 0.85; target_entity_id = $eid
        proposed_record = @{
            title = "Lymphatic Bliss: Face + Body Reset"
            description = "Gentle wellness/self-care class supporting circulation and tension release: light movement, gentle breathwork, posture awareness, fluid mobility, relaxation. 60 min with Toni Icard, Studio #210. Tuesday 8:00am in both observed weeks. $obs Week of 6/11 ALSO showed a Thursday 8:00am session - single-week extra, not included here."
            schedule_days = @("tuesday")
            schedule_start_time = "08:00"; schedule_end_time = "09:00"
            location_name = $ven; provider_name = $ven; cost = $cost
            contact_phone = "928-208-7477"; contact_url = $src
            tags = @("wellness","fitness")
        }
    },
    @{  # pairs with pending contribution 613
        entity_type = "program"; submission_name = $ven; source_url = $src
        confidence = 0.85; target_entity_id = $eid
        proposed_record = @{
            title = "Pranayama Vinyasa Yoga"
            description = "Dynamic class integrating pranayama (yogic breathing) with mindful vinyasa movement; builds heat, strength and flexibility. 60 min with Monique Day, Studio #210. Tuesday 9:30am in both observed weeks. $obs"
            schedule_days = @("tuesday")
            schedule_start_time = "09:30"; schedule_end_time = "10:30"
            location_name = $ven; provider_name = $ven; cost = $cost
            contact_phone = "928-208-7477"; contact_url = $src
            tags = @("yoga")
        }
    },
    @{  # pairs with pending contribution 615
        entity_type = "program"; submission_name = $ven; source_url = $src
        confidence = 0.85; target_entity_id = $eid
        proposed_record = @{
            title = "Slow Flow Hip Yoga"
            description = "Slow-flow yoga focused on hip opening and mobility; gentle flowing movement with breathwork. 60 min with Adrianna Gardocki, Studio #210. Tuesday 5:15pm in both observed weeks. $obs"
            schedule_days = @("tuesday")
            schedule_start_time = "17:15"; schedule_end_time = "18:15"
            location_name = $ven; provider_name = $ven; cost = $cost
            contact_phone = "928-208-7477"; contact_url = $src
            tags = @("yoga")
        }
    },
    @{  # pairs with pending contribution 616
        entity_type = "program"; submission_name = $ven; source_url = $src
        confidence = 0.85; target_entity_id = $eid
        proposed_record = @{
            title = "Mat Pilates"
            description = "Balanced mat Pilates emphasizing control, precision and alignment; builds strength, flexibility and posture. 60 min with Ja'nette Hodge, Studio #210. Tuesday 6:30pm in both observed weeks. $obs"
            schedule_days = @("tuesday")
            schedule_start_time = "18:30"; schedule_end_time = "19:30"
            location_name = $ven; provider_name = $ven; cost = $cost
            contact_phone = "928-208-7477"; contact_url = $src
            tags = @("pilates","fitness")
        }
    }
)

foreach ($p in $payloads) {
    if ($WhatIf) {
        Write-Host ("WHATIF {0,-36} conf={1} days={2} {3}-{4}" -f $p.proposed_record.title, $p.confidence, ($p.proposed_record.schedule_days -join "/"), $p.proposed_record.schedule_start_time, $p.proposed_record.schedule_end_time)
        continue
    }
    $body = $p | ConvertTo-Json -Depth 6
    try {
        $r = Invoke-RestMethod -Uri "$base/api/ingest/contribution" -Method POST `
            -Headers @{ Authorization = "Bearer $tok" } -ContentType "application/json" -Body $body
        Write-Host ("{0,-36} -> {1}  id={2}" -f $p.proposed_record.title, $r.status, $r.id)
    } catch {
        $code = $null
        if ($_.Exception.Response) { $code = [int]$_.Exception.Response.StatusCode }
        Write-Host ("{0,-36} -> FAILED HTTP {1}: {2}" -f $p.proposed_record.title, $code, $_.ErrorDetails.Message)
    }
}
