# resend_eightlotus_tue.ps1 — post the 5 new Eight Lotus TUESDAY findings from the
# 2026-06-04 continuation session (sandbox .env mount was stale -> 401; run locally).
# (PowerShell 5.1 compatible; reads INGEST_API_TOKEN from .env, never prints it)
$ErrorActionPreference = "Stop"
$base = "https://havasu-chat-production.up.railway.app"

$line = (Get-Content .env | Where-Object { $_ -match '^INGEST_API_TOKEN=' } | Select-Object -First 1)
if (-not $line) { Write-Host "FAIL: no INGEST_API_TOKEN in .env"; exit 1 }
$tok = $line.Split('=',2)[1].Trim().Trim('"').Trim("'")

$eid = "35fcab51-bf9a-4cf9-ac98-816ce54d95d9"
$src = "https://www.8lotuswellness.com/book-class"
$ven = "Eight Lotus Center for Wellness"
$cost = "`$20 walk-in; `$100/mo unlimited; `$150 10-class"
$obs = "First observed Tue 6/9/26 on the live Mindbody booking feed (Tuesdays previously had no classes - new lineup; single-week observation)."

$payloads = @(
    @{
        entity_type = "program"; submission_name = $ven; source_url = $src
        confidence = 0.60; target_entity_id = $eid
        proposed_record = @{
            title = "Lymphatic Bliss: Face + Body Reset"
            description = "Gentle wellness/self-care class supporting circulation and tension release: light movement, gentle breathwork, posture awareness, fluid mobility, relaxation. 60 min with Toni Icard, Eight Lotus Studio #210. $obs"
            schedule_days = @("tuesday")
            schedule_start_time = "08:00"; schedule_end_time = "09:00"
            location_name = $ven; provider_name = $ven; cost = $cost
            contact_phone = "928-208-7477"; contact_url = $src
            tags = @("wellness","fitness")
        }
    },
    @{
        entity_type = "program"; submission_name = $ven; source_url = $src
        confidence = 0.60; target_entity_id = $eid
        proposed_record = @{
            title = "Pranayama Vinyasa Yoga"
            description = "Dynamic class integrating pranayama (yogic breathing) with mindful vinyasa movement; builds heat, strength and flexibility. 60 min with Monique Day, Eight Lotus Studio #210. $obs"
            schedule_days = @("tuesday")
            schedule_start_time = "09:30"; schedule_end_time = "10:30"
            location_name = $ven; provider_name = $ven; cost = $cost
            contact_phone = "928-208-7477"; contact_url = $src
            tags = @("yoga")
        }
    },
    @{
        entity_type = "program"; submission_name = $ven; source_url = $src
        confidence = 0.55; target_entity_id = $eid
        proposed_record = @{
            title = "Havasu Hula Dance"
            description = "Hawaiian hula dance class - technique plus low-impact cardio in a follow-along style. 60 min with Kahealani Cherland. Observed Tue 1:00pm 6/9/26 on the live Mindbody feed; NOTE the 6/4/26 week-1 observation had Hula on Thursday 1:00pm - day may have moved or both days run; confidence kept low until a second week confirms."
            schedule_days = @("tuesday")
            schedule_start_time = "13:00"; schedule_end_time = "14:00"
            location_name = $ven; provider_name = $ven; cost = $cost
            contact_phone = "928-208-7477"; contact_url = $src
            tags = @("dance")
        }
    },
    @{
        entity_type = "program"; submission_name = $ven; source_url = $src
        confidence = 0.60; target_entity_id = $eid
        proposed_record = @{
            title = "Slow Flow Hip Yoga"
            description = "Slow-flow yoga focused on hip opening and mobility; gentle flowing movement with breathwork. 60 min with Adrianna Gardocki, Eight Lotus Studio #210. $obs"
            schedule_days = @("tuesday")
            schedule_start_time = "17:15"; schedule_end_time = "18:15"
            location_name = $ven; provider_name = $ven; cost = $cost
            contact_phone = "928-208-7477"; contact_url = $src
            tags = @("yoga")
        }
    },
    @{
        entity_type = "program"; submission_name = $ven; source_url = $src
        confidence = 0.60; target_entity_id = $eid
        proposed_record = @{
            title = "Mat Pilates"
            description = "Balanced mat Pilates emphasizing control, precision and alignment; builds strength, flexibility and posture. 60 min with Ja'nette Hodge, Eight Lotus Studio #210. $obs"
            schedule_days = @("tuesday")
            schedule_start_time = "18:30"; schedule_end_time = "19:30"
            location_name = $ven; provider_name = $ven; cost = $cost
            contact_phone = "928-208-7477"; contact_url = $src
            tags = @("pilates","fitness")
        }
    }
)

foreach ($p in $payloads) {
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
