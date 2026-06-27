# RAPID DESIGN.md

> Design system for RAPID — Departmental Intelligence Operating System.
> Generated with the awesome-design-md skill format.

---

## 1. Brand Essence

**Tagline:** "Your organization's intelligence layer."

**Canvas type:** `dark`

**Core feeling:** Authority, clarity, trust, intelligence. A command center that is serious but not cold — precise but approachable.

**Aesthetic in one sentence:** Deep navy command center with indigo-violet intelligence accents — where enterprise power meets AI clarity.

---

## 2. Color Palette

```
Background:        #060A14   (deepest navy — main page canvas)
Surface:           #0C1220   (primary surface — sidebar, topbar)
Surface Raised:    #101929   (cards, panels)
Surface Elevated:  #162035   (hover states, selected items)
Surface High:      #1B2740   (form inputs, chips)
Border:            #1A2840   (default borders)
Border Subtle:     #0F1C30   (very subtle dividers)
Border Active:     #2D4A7A   (focused / active borders)

Primary:           #4C6EF5   (RAPID indigo — main accent)
Primary Hover:     #3B5CE0   (hover state)
Primary Dim:       rgba(76,110,245,0.15)   (tinted backgrounds)
Primary Glow:      rgba(76,110,245,0.25)   (focus rings, glows)
Secondary:         #7B5CF6   (violet — used in gradients with Primary)
Gradient:          linear-gradient(135deg, #4C6EF5, #7B5CF6)

Text Primary:      #E8EFFF   (main body text — blue-white)
Text Secondary:    #6880A4   (muted text, labels)
Text Muted:        #334466   (very faint — disabled, placeholders)
Text On Primary:   #FFFFFF   (text on accent backgrounds)

Success:           #0EA371   (emerald green)
Success Dim:       rgba(14,163,113,0.12)
Warning:           #E8A020   (amber)
Warning Dim:       rgba(232,160,32,0.12)
Error:             #E84040   (red)
Error Dim:         rgba(232,64,64,0.12)
Info:              #4C6EF5   (same as Primary)

Role — Admin:      #E84040 / Error Dim
Role — CEO:        #E8A020 / Warning Dim
Role — DeptHead:   #4C6EF5 / Primary Dim
Role — Manager:    #0EA371 / Success Dim
Role — Employee:   #6880A4 / Surface High
```

---

## 3. Typography

```
Display font:   'Inter', -apple-system, BlinkMacSystemFont, sans-serif
Body font:      'Inter', sans-serif
Mono font:      'JetBrains Mono', 'Fira Code', monospace

Scale:
  display-2xl:  48px / 1.1  / 700   (hero headlines)
  display-xl:   40px / 1.15 / 700   (page hero)
  display-lg:   32px / 1.2  / 700   (section hero)
  heading-xl:   24px / 1.25 / 700   (page titles)
  heading-lg:   20px / 1.3  / 700   (section headings)
  heading-md:   16px / 1.4  / 600   (card titles, panel headers)
  heading-sm:   14px / 1.4  / 600   (sub-headings)
  body-lg:      15px / 1.6  / 400   (primary body)
  body-md:      14px / 1.6  / 400   (standard body)
  body-sm:      13px / 1.55 / 400   (secondary body, descriptions)
  caption:      12px / 1.5  / 400   (captions, timestamps)
  label:        11px / 1.4  / 600   / letter-spacing: 0.07em / UPPERCASE (section labels, nav labels)

Letter spacing:
  headings:   -0.01em (slightly tight — precision feel)
  labels:     0.07em uppercase (structured, organized)
  body:       0 (natural)
```

---

## 4. Spacing & Layout

```
Base unit:            4px
Sidebar width:        220px
Topbar height:        56px
Container max-width:  1280px
Content max-width:    960px

Spacing scale:
  xs:   4px
  sm:   8px
  md:   16px
  lg:   24px
  xl:   32px
  2xl:  48px
  3xl:  64px

Section padding (vertical):  32px / 24px (desktop / mobile)
Card padding:                 20px / 16px
Sidebar item padding:         8px 10px
```

---

## 5. Border & Shadow

```
Border radius:
  none:  0px
  xs:    4px   (badges, chips)
  sm:    6px   (small elements)
  md:    8px   (nav items, inputs)
  lg:    12px  (cards)
  xl:    16px  (large cards, modals)
  full:  9999px (pills, avatars)

Border width:   1px
Border color:   #1A2840 (default), #2D4A7A (active/focus)

Shadows:
  sm:   0 1px 3px rgba(0,0,0,0.4), 0 1px 2px rgba(0,0,0,0.3)
  md:   0 4px 12px rgba(0,0,0,0.4), 0 2px 4px rgba(0,0,0,0.3)
  lg:   0 8px 24px rgba(0,0,0,0.5), 0 4px 8px rgba(0,0,0,0.3)
  xl:   0 16px 48px rgba(0,0,0,0.6), 0 8px 16px rgba(0,0,0,0.4)
  glow: 0 0 0 3px rgba(76,110,245,0.25)
  card: 0 1px 3px rgba(0,0,0,0.4), inset 0 1px 0 rgba(255,255,255,0.03)
```

---

## 6. Component Patterns

### Buttons
```
Primary:
  bg:      linear-gradient(135deg, #4C6EF5, #6366F1)
  text:    #FFFFFF
  radius:  8px
  padding: 10px 20px
  weight:  600
  hover:   opacity 0.88, translateY(-1px)
  shadow:  0 2px 8px rgba(76,110,245,0.35)

Secondary:
  bg:      #162035
  border:  1px solid #1A2840
  text:    #6880A4
  hover:   border-color #4C6EF5, text #4C6EF5

Ghost:
  bg:      transparent
  text:    #6880A4
  hover:   bg #162035

Danger:
  bg:      rgba(232,64,64,0.1)
  border:  1px solid rgba(232,64,64,0.3)
  text:    #E84040
  hover:   bg #E84040, text white

Sizes:
  sm:  height=30px  px=12px  font=12px
  md:  height=36px  px=16px  font=13px
  lg:  height=44px  px=20px  font=15px
```

### Cards
```
Background:  #101929
Border:      1px solid #1A2840
Radius:      12px
Padding:     20px
Shadow:      0 1px 3px rgba(0,0,0,0.4), inset 0 1px 0 rgba(255,255,255,0.03)
Hover:       border-color #2D4A7A, translateY(-2px)
Top accent:  inset 0 1px 0 rgba(76,110,245,0.2) on active/selected cards
```

### Inputs
```
Background:  #162035
Border:      1px solid #1A2840
Focus:       border-color #4C6EF5, box-shadow 0 0 0 3px rgba(76,110,245,0.2)
Radius:      8px
Padding:     10px 14px
Font size:   14px
Placeholder: #334466
```

### Navigation (Sidebar)
```
Style:          Left sidebar, fixed
Background:     #0C1220
Width:          220px
Item radius:    8px
Item padding:   8px 10px
Section label:  11px / 600 / uppercase / #334466
Active item:    bg rgba(76,110,245,0.12), color #4C6EF5, left border 2px solid #4C6EF5
Active icon:    #4C6EF5
Hover item:     bg #162035, color #E8EFFF
```

---

## 7. Motion & Animation

```
Duration:
  instant:  0ms
  fast:     120ms
  normal:   200ms
  slow:     300ms

Easing:
  default:  cubic-bezier(0.16, 1, 0.3, 1)
  in-out:   cubic-bezier(0.4, 0, 0.2, 1)
  spring:   cubic-bezier(0.34, 1.56, 0.64, 1)

Transitions:
  hover:   all 150ms cubic-bezier(0.16, 1, 0.3, 1)
  page:    opacity 200ms ease
  card:    transform 150ms ease, border-color 150ms ease, box-shadow 150ms ease
```

---

## 8. Iconography

```
Icon library:  Unicode emoji for MVP (⊞ 📁 💬 ✅ 🔍 etc.)
               Upgrade path: Lucide React or Phosphor Icons
Icon size:     sm=14px  md=16px  lg=20px
Color:         Text Secondary (#6880A4) default, Primary (#4C6EF5) active

Avatar style:  Circular, gradient bg (Primary → Secondary)
               First letter of name, bold, white

Status dots:   7px circle
  Online/active:  #0EA371
  Pending:        #E8A020
  Offline/error:  #E84040
  Inactive:       #334466
```

---

## 9. Voice & Tone

```
Copy style:      Precise and direct. No filler words. Every word earns its place.
CTA language:    "Sign in" / "Configure" / "Apply" / "Approve" / "Launch RAPID"
Heading style:   Sentence case for UI labels, Title Case for page headings
Number format:   Compact (1.2k, 4.5M) for dashboards, full for reports
Error messages:  Specific and actionable. "Invalid credentials" not "Something went wrong."
Empty states:    Helpful context + next action. Not just "No data."
Role labels:     Title Case — "Dept Head" not "dept_head"
Timestamps:      Relative for recent (2h ago), absolute for older (May 12)
```
