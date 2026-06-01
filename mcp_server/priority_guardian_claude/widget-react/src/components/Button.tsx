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
      sm: { padding: '16px 12px', fontSize: '12px' },
      md: { padding: '15px 16px', fontSize: '14px' },
    }

    const colorStyles: Record<ButtonColor, Record<ButtonVariant, { base: CSSProperties; hover: CSSProperties }>> = {
      primary: {
        solid: {
          base: {
            background: 'var(--color-background-info, #D6E4F6)',
            color: 'var(--color-text-info, #3266AD)',
            border: 'none',
          },
          hover: { opacity: 0.9 },
        },
        ghost: {
          base: {
            background: 'transparent',
            color: 'var(--color-text-info, #3266AD)',
            border: 'none',
          },
          hover: { background: 'var(--color-background-info, #D6E4F6)' },
        },
        outline: {
          base: {
            background: 'transparent',
            color: 'var(--color-text-info, #3266AD)',
            border: '1px solid var(--color-border-info, #4682D5)',
          },
          hover: { background: 'var(--color-background-info, #D6E4F6)' },
        },
      },
      secondary: {
        solid: {
          base: {
            background: 'var(--color-background-secondary, #F5F4ED)',
            color: 'var(--color-text-primary, #141413)',
            border: 'none',
          },
          hover: { opacity: 0.9 },
        },
        ghost: {
          base: {
            background: 'transparent',
            color: 'var(--color-text-secondary, #73726C)',
            border: 'none',
          },
          hover: { background: 'var(--color-background-secondary, #F5F4ED)' },
        },
        outline: {
          base: {
            background: 'transparent',
            color: 'var(--color-text-secondary, #73726C)',
            border: '1px solid var(--color-border-primary, rgba(31,30,29,0.4))',
          },
          hover: { background: 'var(--color-background-secondary, #F5F4ED)' },
        },
      },
      danger: {
        solid: {
          base: {
            background: 'var(--color-background-danger, #F7ECEC)',
            color: 'var(--color-text-danger, #7F2C28)',
            border: 'none',
          },
          hover: { opacity: 0.9 },
        },
        ghost: {
          base: {
            background: 'transparent',
            color: 'var(--color-text-danger, #7F2C28)',
            border: 'none',
          },
          hover: { background: 'var(--color-background-danger, #F7ECEC)' },
        },
        outline: {
          base: {
            background: 'transparent',
            color: 'var(--color-text-danger, #7F2C28)',
            border: '1px solid var(--color-border-danger, #A73D39)',
          },
          hover: { background: 'var(--color-background-danger, #F7ECEC)' },
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
      outline: isFocused ? '2px solid var(--color-ring-primary, rgba(20,20,19,0.7))' : 'none',
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
