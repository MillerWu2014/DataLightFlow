---
name: Precision Workbench
colors:
  surface: '#faf9fe'
  surface-dim: '#dad9df'
  surface-bright: '#faf9fe'
  surface-container-lowest: '#ffffff'
  surface-container-low: '#f4f3f8'
  surface-container: '#eeedf3'
  surface-container-high: '#e9e7ed'
  surface-container-highest: '#e3e2e7'
  on-surface: '#1a1b1f'
  on-surface-variant: '#414755'
  inverse-surface: '#2f3034'
  inverse-on-surface: '#f1f0f5'
  outline: '#717786'
  outline-variant: '#c1c6d7'
  surface-tint: '#005bc1'
  primary: '#0058bc'
  on-primary: '#ffffff'
  primary-container: '#0070eb'
  on-primary-container: '#fefcff'
  inverse-primary: '#adc6ff'
  secondary: '#405e96'
  on-secondary: '#ffffff'
  secondary-container: '#a1befd'
  on-secondary-container: '#2d4c83'
  tertiary: '#9e3d00'
  on-tertiary: '#ffffff'
  tertiary-container: '#c64f00'
  on-tertiary-container: '#fffbff'
  error: '#ba1a1a'
  on-error: '#ffffff'
  error-container: '#ffdad6'
  on-error-container: '#93000a'
  primary-fixed: '#d8e2ff'
  primary-fixed-dim: '#adc6ff'
  on-primary-fixed: '#001a41'
  on-primary-fixed-variant: '#004493'
  secondary-fixed: '#d8e2ff'
  secondary-fixed-dim: '#adc6ff'
  on-secondary-fixed: '#001a41'
  on-secondary-fixed-variant: '#26467d'
  tertiary-fixed: '#ffdbcc'
  tertiary-fixed-dim: '#ffb595'
  on-tertiary-fixed: '#351000'
  on-tertiary-fixed-variant: '#7c2e00'
  background: '#faf9fe'
  on-background: '#1a1b1f'
  surface-variant: '#e3e2e7'
typography:
  display-lg:
    fontFamily: Geist
    fontSize: 40px
    fontWeight: '700'
    lineHeight: 48px
    letterSpacing: -0.02em
  headline-lg:
    fontFamily: Geist
    fontSize: 32px
    fontWeight: '600'
    lineHeight: 40px
    letterSpacing: -0.01em
  headline-md:
    fontFamily: Geist
    fontSize: 24px
    fontWeight: '600'
    lineHeight: 32px
  body-lg:
    fontFamily: Geist
    fontSize: 16px
    fontWeight: '400'
    lineHeight: 24px
  body-md:
    fontFamily: Geist
    fontSize: 14px
    fontWeight: '400'
    lineHeight: 20px
  label-mono:
    fontFamily: JetBrains Mono
    fontSize: 12px
    fontWeight: '500'
    lineHeight: 16px
    letterSpacing: 0.05em
  headline-lg-mobile:
    fontFamily: Geist
    fontSize: 24px
    fontWeight: '600'
    lineHeight: 32px
rounded:
  sm: 0.25rem
  DEFAULT: 0.5rem
  md: 0.75rem
  lg: 1rem
  xl: 1.5rem
  full: 9999px
spacing:
  base: 8px
  xs: 4px
  sm: 12px
  md: 16px
  lg: 24px
  xl: 32px
  gutter: 16px
  margin: 24px
---

## Brand & Style

This design system is built for high-performance AI workflows, prioritizing clarity, focus, and technical sophistication. It draws heavily from **Minimalism** and **Modern Corporate** aesthetics, utilizing a restrained palette and generous whitespace to reduce cognitive load during complex data analysis.

The visual language balances the clinical precision of a developer tool with the refined elegance of premium hardware. Key characteristics include:
- **Clarity over Decoration:** Every element serves a functional purpose; decorative flourishes are replaced by intentional alignment and typographic hierarchy.
- **Controlled Depth:** Depth is communicated through subtle layer stacking and light-diffusing glass effects rather than heavy shadows.
- **Professionalism:** The interface maintains a neutral, objective tone to ensure that user content—whether code, data, or AI-generated text—remains the focal point.

## Colors

The color palette is anchored in a systematic "Apple-inspired" range. The primary objective is to use color only where it signifies action, status, or data importance.

### Core Palette
- **Primary:** Apple Blue (#007AFF) is reserved exclusively for primary calls to action, active states, and focus indicators.
- **Surface:** Pure White (#FFFFFF) in light mode provides a "paper" feel, while Deep Charcoal (#171717) in dark mode provides a "terminal" feel.
- **Stroke:** Soft Gray (#E5E5E5) defines boundaries without creating visual noise.

### Functional Status (4D Scoring)
To support the 4D scoring visualization, use the following semantic mapping:
- **Critical (1-2):** Status Red (#FF3B30) for immediate attention.
- **Warning (3):** Status Amber (#FF9500) for average or cautious scores.
- **Optimal (4-5):** Status Green (#34C759) for high-performance metrics.

## Typography

This design system utilizes **Geist** for its systematic, technical, yet approachable character. It provides the high-contrast hierarchy necessary for a professional workbench.

- **Headings:** Use bold weights and tighter letter-spacing to create a strong visual anchor for sections.
- **Body:** Standardized at 14px and 16px for optimal readability in data-dense environments.
- **Mono:** **JetBrains Mono** is introduced for labels, status badges, and code editing areas to reinforce the "workbench" utility.
- **Accessibility:** Maintain a minimum contrast ratio of 4.5:1 for all text elements.

## Layout & Spacing

The design system employs a strict **8px grid system**. All dimensions, padding, and margins must be multiples of 8 (or 4 for micro-adjustments).

### Layout Model
- **Workbench Layout:** A fixed left sidebar (width: 280px) for navigation and task management, a fluid center area for the primary editor or visualization, and an optional right inspector panel (width: 320px).
- **Margins & Gutters:** Global page margins are set to 24px. Internal component gutters are 16px.
- **Responsive Behavior:** On tablet, the right inspector collapses into a modal overlay. On mobile, the layout reflows to a single column with the task sidebar accessible via a bottom sheet.

## Elevation & Depth

This design system uses **Tonal Layers** and **Glassmorphism** to establish hierarchy without relying on traditional drop shadows.

1.  **Level 0 (Base):** Pure white (#FFFFFF) or Deep Charcoal (#171717). The canvas.
2.  **Level 1 (Sub-surface):** Used for sidebars and secondary navigation. Employs a backdrop-blur (20px) with 80% opacity.
3.  **Level 2 (Raised):** Cards and content containers. Defined by a 1px border (#E5E5E5) rather than a shadow.
4.  **Level 3 (Overlay):** Modals and dropdowns. These use a very soft, diffused shadow (0px 4px 24px rgba(0,0,0,0.04)) and a frosted glass background to separate them from the workbench.

## Shapes

The shape language is consistent and rhythmic. A standard **8px (0.5rem)** radius is used for the majority of UI components, reflecting a modern, hardware-like precision.

- **Buttons & Inputs:** 8px (Default).
- **Cards & Modals:** 12px (Large).
- **Status Badges & Chips:** Fully rounded (Pill) to distinguish them from interactive buttons.
- **Code Blocks:** 4px (Small) to maintain a more structured, "blocky" feel for technical content.

## Components

### Buttons & Actions
- **Primary:** Solid Apple Blue with white text. High contrast, 8px corner radius.
- **Secondary:** Transparent background with a 1px Gray-200 border.
- **Ghost:** No border or background until hover. Used for toolbar icons.

### 4D Scoring Visualization
- **Radar Charts:** Use thin 1px strokes in Gray-300 for the grid. The fill should be primary blue at 10% opacity with a 2px solid primary stroke.
- **Segmented Bars:** 5 distinct segments. Fill segments according to the score using the Status Red/Amber/Green values. Unfilled segments should be a very light gray (#F2F2F7).

### Task Sidebar
- **Status Badges:** Use the Mono font at 10px. Labels should be uppercase. 
- **Active State:** A subtle vertical blue line (2px width) on the far left of the active task item.

### Inputs & Editors
- **Code Editor:** Background should be slightly darker than the base surface (e.g., #F9F9F9 in light mode). Use JetBrains Mono for all content.
- **Form Fields:** 1px border that turns Apple Blue on focus. Labels sit 4px above the input in Geist Bold 12px.