# Clarity — User-Facing Warnings

Copy and implementation notes for user-facing warnings about known limitations.

---

## 1. OAuth Consent Screen

### Location
- `backend/templates/oauth_consent_en.html`
- `backend/templates/oauth_consent_de.html`

### English Copy

Add below the permissions list, before the Allow/Deny buttons:

```html
<div class="browser-warning">
  <p>⚠️ <strong>Important:</strong> Always reconnect from this browser. 
  Using a different browser or device will create a new account and you won't 
  have access to your previous data.</p>
</div>
```

### German Copy

```html
<div class="browser-warning">
  <p>⚠️ <strong>Wichtig:</strong> Verbinde dich immer über diesen Browser erneut. 
  Bei Verwendung eines anderen Browsers oder Geräts wird ein neues Konto erstellt 
  und du hast keinen Zugriff auf deine bisherigen Daten.</p>
</div>
```

### Suggested CSS

```css
.browser-warning {
  background-color: #fff3cd;
  border: 1px solid #ffc107;
  border-radius: 4px;
  padding: 12px 16px;
  margin: 16px 0;
  font-size: 14px;
}

.browser-warning p {
  margin: 0;
  color: #856404;
}
```

---

## 2. `get_my_clusters` Response (No History)

### Location
- `mcp_server/clarity/tools/get_my_clusters.py`

### Current Text
```python
text="No previous brain dump found. Starting fresh."
```

### Updated Text
```python
text="No previous brain dump found. Starting fresh. (If you expected to see existing data, you may have reconnected from a different browser — data is browser-specific.)"
```

---

## 3. App Store / OpenAI Submission Description

### Location
- OpenAI app submission form (when submitting to marketplace)
- Any public-facing app description

### Copy

Add to "Known Limitations" or "Important Notes" section:

```
**Browser-Specific Data**

Your Clarity data is linked to your browser session. If you disconnect and 
reconnect from a different browser or device, a new account will be created. 
For best results, always reconnect from the same browser where you first 
set up Clarity.
```

---

## 4. Help / FAQ (Future)

If you add a help section or FAQ:

### Q: I reconnected but my clusters are gone. What happened?

**A:** Your data is linked to the browser where you first connected. If you 
reconnected from a different browser or device, a new account was created. 
Your original data still exists but is not accessible from this session.

To prevent this in the future, always reconnect from the same browser.

If you need to recover important data, contact support with details about 
when you created your clusters.

---

## Implementation Checklist

- [ ] Add warning to `oauth_consent_en.html`
- [ ] Add warning to `oauth_consent_de.html`
- [ ] Update `get_my_clusters.py` response text
- [ ] Add note to OpenAI app submission (when ready)

---

*Last updated: December 16, 2025*
