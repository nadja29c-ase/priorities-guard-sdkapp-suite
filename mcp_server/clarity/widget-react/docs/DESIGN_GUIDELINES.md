# App Design Guidelines
*Design guidelines for developers building on the Apps SDK*

## Overview

Apps are developer-built experiences that live inside ChatGPT. They extend what users can do without breaking the flow of conversation, appearing through lightweight cards, carousels, fullscreen views, and other display modes that integrate seamlessly into ChatGPT's interface while maintaining its clarity, trust, and voice.

---

## Best Practices

Apps are most valuable when they help people accomplish meaningful tasks directly within ChatGPT, without breaking the conversational flow. The goal is to design experiences that feel consistent, useful, and trustworthy while extending ChatGPT in ways that add real value. 

**Good use cases:** booking a ride, ordering food, checking availability, or tracking a delivery. These are tasks that are conversational, time bound, and easy to summarize visually with a clear call to action.

**Poor use cases:** pasting in long form content from a website, requiring complex multi step workflows, or using the space for ads or irrelevant messaging.

---

## Principles

- **Conversational:** Experiences should feel like a natural extension of ChatGPT, fitting seamlessly into the conversational flow and UI.
- **Intelligent:** Tools should be aware of conversation context, supporting and anticipating user intent. Responses and UI should feel individually relevant.
- **Simple:** Each interaction should focus on a single clear action or outcome. Information and UI should be reduced to the absolute minimum to support the context.
- **Responsive:** Tools should feel fast and lightweight, enhancing conversation rather than overwhelming it.
- **Accessible:** Designs must support a wide range of users, including those who rely on assistive technologies.

---

## Boundaries

ChatGPT controls system-level elements such as voice, chrome, styles, navigation, and composer. Developers provide value by customizing content, brand presence, and actions inside the system framework.

This balance ensures that all apps feel native to ChatGPT while still expressing unique brand value.

---

## Visual Design Guidelines

### Color

System-defined palettes ensure actions and responses always feel consistent with ChatGPT.

**Rules of thumb:**
- Use system colors for text, icons, and spatial elements like dividers
- Partner brand accents (logos/icons) should not override backgrounds or text colors
- Avoid custom gradients or patterns that break ChatGPT's minimal look
- Use brand accent colors on primary buttons inside app display modes
- Don't apply colors to backgrounds in text areas

### Typography

ChatGPT uses platform-native system fonts (SF Pro on iOS, Roboto on Android).

**Rules of thumb:**
- Always inherit the system font stack
- Use partner styling (bold, italic, highlights) only within content areas
- Limit variation in font size as much as possible
- Don't use custom fonts, even in fullscreen modes

### Spacing & Layout

Consistent margins, padding, and alignment keep content scannable and predictable.

**Rules of thumb:**
- Use system grid spacing for cards, collections, and panels
- Keep padding consistent and avoid cramming or edge-to-edge text
- Respect system specified corner rounds when possible
- Maintain visual hierarchy with headline, supporting text, and CTA in clear order

### Icons & Imagery

**Rules of thumb:**
- Use either system icons or custom iconography that fits ChatGPT's visual world (monochromatic and outlined)
- Do not include your logo as part of the response (ChatGPT appends it automatically)
- All imagery must follow enforced aspect ratios to avoid distortion
- Provide alt text for all images

---

## Accessibility

Every partner experience should be usable by the widest possible audience.

**Requirements:**
- Text and background must maintain minimum contrast ratio (WCAG AA)
- Provide alt text for all images
- Support text resizing without breaking layouts

---

## Display Modes

### 1. Inline Card
Lightweight, single-purpose widgets embedded directly in conversation.

**Rules of thumb:**
- Limit primary actions per card to two maximum
- No deep navigation or multiple views within a card
- No nested scrolling - cards should auto-fit their content
- No duplicative inputs - don't replicate ChatGPT features

### 2. Fullscreen
Immersive experiences for multi-step workflows.

**Rules of thumb:**
- Design your UX to work with the system composer (always present)
- Use fullscreen to deepen engagement, not replicate your native app wholesale

---

## Tone & Content

- Keep content concise and scannable
- Always context-driven: content should respond to what the user asked
- Avoid spam, jargon, or promotional language
- Focus on helpfulness and clarity over brand personality
