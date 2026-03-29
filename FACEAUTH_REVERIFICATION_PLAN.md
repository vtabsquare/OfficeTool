# FaceAuth Periodic Re-Verification Alert System - Implementation Plan

## Executive Summary

Implement a system where HR Tool displays alert notifications from FaceAuth's Dataverse database, prompting users to re-verify their face every 2 hours. Clicking the notification redirects to FaceAuth for verification, then returns to HR Tool.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              DATAVERSE (Source of Truth)                     │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │  crc6f_face_verification_alerts                                      │    │
│  │  - employee_id, last_verified, next_verification_due, status         │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                    ┌─────────────────┴─────────────────┐
                    ▼                                   ▼
        ┌───────────────────┐               ┌───────────────────┐
        │   FaceAuth App    │               │    HR Tool App    │
        │  (Writes alerts)  │               │  (Reads alerts)   │
        └───────────────────┘               └───────────────────┘
                    │                                   │
                    │         ┌─────────────┐           │
                    └────────►│   User      │◄──────────┘
                              │  Browser    │
                              └─────────────┘
```

---

## Phase 1: Database Schema (Dataverse)

### Option A: Use Existing FaceAuth Table (Recommended)
If FaceAuth already has a verification tracking table, HR Tool should READ from it.

### Option B: Create Shared Alert Table
If no table exists, create one that both apps can access:

**Table: `crc6f_face_verification_status`**
| Field | Type | Description |
|-------|------|-------------|
| `crc6f_employee_id` | String (PK) | Employee ID (e.g., EMP015) |
| `crc6f_email` | String | Employee email |
| `crc6f_last_verified_at` | DateTime | Last successful face verification |
| `crc6f_next_verification_due` | DateTime | When next verification is required |
| `crc6f_verification_interval_hours` | Int | Hours between verifications (default: 2) |
| `crc6f_status` | Choice | `verified`, `pending`, `overdue` |
| `crc6f_alert_dismissed_at` | DateTime | When user dismissed the alert (optional) |

**Key Design Decisions:**
- FaceAuth WRITES to this table after each verification
- HR Tool READS from this table to show alerts
- Single source of truth = no sync issues

---

## Phase 2: Backend API (HR Tool - unified_server.py)

### 2.1 New Endpoint: Check Verification Status

```python
@app.route("/api/faceauth/verification-status", methods=["GET"])
def get_faceauth_verification_status():
    """
    Check if current user needs face re-verification.
    Returns: { needs_verification: bool, next_due: datetime, last_verified: datetime }
    """
```

### 2.2 New Endpoint: Get Verification Redirect URL

```python
@app.route("/api/faceauth/reverify-url", methods=["GET"])
def get_faceauth_reverify_url():
    """
    Generate a signed URL for re-verification flow.
    Returns: { redirect_url: string }
    """
```

### 2.3 New Endpoint: Acknowledge Alert (Optional)

```python
@app.route("/api/faceauth/dismiss-alert", methods=["POST"])
def dismiss_faceauth_alert():
    """
    User dismisses alert temporarily (snooze for X minutes).
    Does NOT reset verification - just hides UI alert.
    """
```

---

## Phase 3: Frontend Implementation (HR Tool)

### 3.1 Notification Component

**File: `components/FaceAuthAlert.js`**

```javascript
// Responsibilities:
// 1. Poll backend every 30 seconds for verification status
// 2. Show non-intrusive alert banner when verification needed
// 3. Handle click → redirect to FaceAuth
// 4. Handle return from FaceAuth → clear alert
```

### 3.2 Alert UI States

| State | UI | Action |
|-------|-----|--------|
| `verified` | No alert | - |
| `due_soon` (< 15 min) | Yellow warning banner | "Verify soon" |
| `overdue` | Red alert banner + bell icon badge | "Verify now" |
| `verifying` | Loading state | Redirect in progress |

### 3.3 Alert Placement Options

1. **Header notification bell** - Badge count includes FaceAuth alerts
2. **Floating banner** - Top of page, dismissible but returns
3. **Modal popup** - For critical overdue (> 30 min past due)

**Recommended:** Combination of #1 and #2

### 3.4 Polling Strategy

```javascript
// Smart polling to reduce server load:
// - If verified: poll every 5 minutes
// - If due in < 30 min: poll every 1 minute
// - If overdue: poll every 30 seconds
// - Use visibility API: pause when tab hidden
```

---

## Phase 4: Re-Verification Flow

### 4.1 Flow Diagram

```
HR Tool                    FaceAuth                   Dataverse
   │                          │                          │
   │ 1. User clicks alert     │                          │
   ├─────────────────────────►│                          │
   │   (redirect with token)  │                          │
   │                          │                          │
   │                          │ 2. Verify face           │
   │                          ├─────────────────────────►│
   │                          │    Update last_verified  │
   │                          │◄─────────────────────────┤
   │                          │                          │
   │ 3. Redirect back         │                          │
   │◄─────────────────────────┤                          │
   │   (with success token)   │                          │
   │                          │                          │
   │ 4. Clear alert, resume   │                          │
   │                          │                          │
```

### 4.2 Token Design for Re-Verification

**Different from login token** - Re-verification token should:
- Be short-lived (5 minutes)
- Include `purpose: "reverification"` claim
- Include `return_url` for seamless redirect back
- NOT grant new session - just update verification timestamp

```javascript
// JWT payload for re-verification
{
  "employee_id": "EMP015",
  "email": "user@example.com",
  "purpose": "reverification",  // <-- Key difference from login
  "return_url": "http://localhost:3000/index.html#/",
  "iat": 1234567890,
  "exp": 1234568190  // 5 min expiry
}
```

### 4.3 FaceAuth Callback Handling

HR Tool needs to handle a NEW callback type:

```javascript
// In index.js - handleFaceAuthCallback()
if (params.get('purpose') === 'reverification') {
  // Don't create new session, just:
  // 1. Update localStorage face_verified timestamp
  // 2. Clear any pending alerts
  // 3. Continue on current page (no redirect to dashboard)
}
```

---

## Phase 5: Edge Cases & Error Handling

### 5.1 Edge Cases

| Scenario | Handling |
|----------|----------|
| User ignores alert for hours | Show modal popup, eventually block actions |
| FaceAuth is down | Graceful degradation - show "Service unavailable" |
| User has multiple tabs open | Use localStorage event to sync alert state |
| User logs out during verification | Clear pending state, require fresh login |
| Network error during redirect | Retry button, don't lose user's work |
| Verification fails (face not recognized) | Show error, allow retry, don't lock out |

### 5.2 Security Considerations

1. **Token tampering**: Verify JWT signature on both apps
2. **Replay attacks**: Include `jti` (JWT ID) claim, track used tokens
3. **CSRF**: Use state parameter in redirect flow
4. **Session hijacking**: Re-verification doesn't extend session, only updates face_verified

### 5.3 Rate Limiting

- Max 10 verification attempts per hour per user
- Prevent alert polling from overwhelming backend (use exponential backoff)

---

## Phase 6: Configuration & Admin

### 6.1 Environment Variables

```bash
# HR Tool backend (.env)
FACEAUTH_REVERIFY_URL=https://biometric.../external-reverify
FACEAUTH_VERIFICATION_INTERVAL_HOURS=2
FACEAUTH_ALERT_SNOOZE_MINUTES=15
FACEAUTH_GRACE_PERIOD_MINUTES=30
```

### 6.2 Admin Dashboard (Future)

- View all users' verification status
- Manually trigger re-verification for specific users
- Adjust verification interval per user/role
- View verification history/audit log

---

## Phase 7: Implementation Order

### Sprint 1: Foundation (2-3 days)
1. [ ] Confirm Dataverse table schema with FaceAuth team
2. [ ] Create `/api/faceauth/verification-status` endpoint
3. [ ] Create `/api/faceauth/reverify-url` endpoint
4. [ ] Basic frontend polling (console.log only)

### Sprint 2: UI & Flow (2-3 days)
5. [ ] Create `FaceAuthAlert.js` component
6. [ ] Integrate alert into header/notification area
7. [ ] Implement redirect to FaceAuth for re-verification
8. [ ] Handle callback with `purpose=reverification`

### Sprint 3: Polish & Edge Cases (1-2 days)
9. [ ] Smart polling (visibility API, adaptive intervals)
10. [ ] Multi-tab sync via localStorage events
11. [ ] Error handling and retry logic
12. [ ] Snooze/dismiss functionality

### Sprint 4: Testing & Deployment (1-2 days)
13. [ ] Unit tests for new endpoints
14. [ ] E2E test: full re-verification flow
15. [ ] Load testing: polling impact on backend
16. [ ] Deploy to staging, then production

---

## Phase 8: Future Enhancements

1. **Push notifications** - WebSocket instead of polling
2. **Mobile app support** - Deep links for re-verification
3. **Biometric alternatives** - Fingerprint, voice as backup
4. **Geofencing** - Only require re-verification when location changes
5. **Risk-based verification** - More frequent for sensitive actions

---

## Questions to Resolve Before Implementation

1. **Does FaceAuth already have a verification tracking table?**
   - If yes, what's the schema? HR Tool will read from it.
   - If no, who creates it? (Recommend: FaceAuth team)

2. **What happens if user never re-verifies?**
   - Soft block (warning only)?
   - Hard block (can't use HR Tool)?
   - After how long?

3. **Should re-verification be required for specific actions only?**
   - E.g., only when approving leave, not for viewing dashboard

4. **What's the exact FaceAuth re-verification endpoint?**
   - Is it `/external-verify` with a different token type?
   - Or a separate `/external-reverify` endpoint?

5. **How should the 2-hour timer work?**
   - From last verification? (User-specific)
   - Fixed schedule? (9am, 11am, 1pm, etc.)
   - Only during work hours?

---

## Summary

This plan provides a **future-proof, scalable** solution for periodic face re-verification:

- **Single source of truth**: Dataverse table owned by FaceAuth
- **Loose coupling**: HR Tool only reads status, doesn't manage verification logic
- **Graceful UX**: Non-blocking alerts with escalation for overdue
- **Security**: Short-lived tokens, purpose-specific claims, no session extension
- **Performance**: Smart polling, visibility-aware, multi-tab sync
- **Extensibility**: Ready for push notifications, mobile, risk-based auth

**Estimated Total Effort**: 6-10 days depending on FaceAuth coordination
