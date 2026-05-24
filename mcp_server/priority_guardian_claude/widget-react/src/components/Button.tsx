import { ButtonHTMLAttributes, forwardRef, useState, CSSProperties } from 'react'

type ButtonColor = 'primary' | 'secondary' | 'danger'
type ButtonVariant = 'solid' | 'ghost' | 'outline'
type ButtonSize = 'sm' | 'md'

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  color?: ButtonColor
  variant?: ButtonVariant
  size?: ButtonSize
}

/**
 * Simple Button component for Claude widget.
 * Uses inline styles with CSS variable tokens — no Tailwind pipeline in this build.
 */
export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ color = 'primary', variant = 'solid', size = 'md', className = '', style, children, ...props }, ref) => {
    const [isHovered, setIsHovered] = useState(false)
    const [isFocused, setIsFocused] = useState(false)

    const sizeStyles: Record<ButtonSize, CSSProperties> = {
      sm: { padding: '6px 12px', fontSize: '12px' },
      md: { padding: '8px 16px', fontSize: '14px' },
    }

    const colorStyles: Record<ButtonColor, Record<ButtonVariant, { base: CSSProperties; hover: CSSProperties }>> = {
      primary: {
        solid: {
          base: {
            background: 'var(--color-background-info-solid, #0285ff)',
            color: '#fff',
            border: 'none',
          },
          hover: { opacity: 0.9 },
        },
        ghost: {
          base: {
            background: 'transparent',
            color: 'var(--color-text-info, #0285ff)',
            border: 'none',
          },
          hover: { background: 'var(--color-background-info-soft-alpha, rgba(2,133,255,0.1))' },
        },
        outline: {
          base: {
            background: 'transparent',
            color: 'var(--color-text-info, #0285ff)',
            border: '1px solid var(--color-border-info, #0285ff)',
          },
          hover: { background: 'var(--color-background-info-soft-alpha, rgba(2,133,255,0.1))' },
        },
      },
      secondary: {
        solid: {
          base: {
            background: 'var(--color-background-secondary, #e5e5e5)',
            color: 'var(--color-text-primary, #171717)',
            border: 'none',
          },
          hover: { opacity: 0.9 },
        },
        ghost: {
          base: {
            background: 'transparent',
            color: 'var(--color-text-secondary, #737373)',
            border: 'none',
          },
          hover: { background: 'var(--color-background-secondary, rgba(0,0,0,0.05))' },
        },
        outline: {
          base: {
            background: 'transparent',
            color: 'var(--color-text-secondary, #737373)',
            border: '1px solid var(--color-border, #e5e5e5)',
          },
          hover: { background: 'var(--color-background-secondary, rgba(0,0,0,0.05))' },
        },
      },
      danger: {
        solid: {
          base: {
            background: 'var(--color-background-danger-solid, #dc2626)',
            color: '#fff',
            border: 'none',
          },
          hover: { opacity: 0.9 },
        },
        ghost: {
          base: {
            background: 'transparent',
            color: 'var(--color-text-danger, #dc2626)',
            border: 'none',
          },
          hover: { background: 'var(--color-background-danger-soft-alpha, rgba(220,38,38,0.1))' },
        },
        outline: {
          base: {
            background: 'transparent',
            color: 'var(--color-text-danger, #dc2626)',
            border: '1px solid var(--color-border-danger, #dc2626)',
          },
          hover: { background: 'var(--color-background-danger-soft-alpha, rgba(220,38,38,0.1))' },
        },
      },
    }

    const colorStyle = colorStyles[color][variant]
    const isDisabled = props.disabled

    const baseStyle: CSSProperties = {
      display: 'inline-flex',
      alignItems: 'center',
      justifyContent: 'center',
      fontWeight: 500,
      borderRadius: '8px',
      transition: 'all 0.15s',
      cursor: isDisabled ? 'not-allowed' : 'pointer',
      opacity: isDisabled ? 0.5 : 1,
      outline: isFocused ? '2px solid var(--color-border-focus, #0285ff)' : 'none',
      outlineOffset: '2px',
      ...sizeStyles[size],
      ...colorStyle.base,
      ...(isHovered && !isDisabled ? colorStyle.hover : {}),
      ...style,
    }

    return (
      <button
        ref={ref}
        className={className}
        style={baseStyle}
        onMouseEnter={(e) => { setIsHovered(true); props.onMouseEnter?.(e) }}
        onMouseLeave={(e) => { setIsHovered(false); props.onMouseLeave?.(e) }}
        onFocus={(e) => { setIsFocused(true); props.onFocus?.(e) }}
        onBlur={(e) => { setIsFocused(false); props.onBlur?.(e) }}
        {...props}
        type={props.type ?? 'button'}
      >
        {children}
      </button>
    )
  }
)

Button.displayName = 'Button'
