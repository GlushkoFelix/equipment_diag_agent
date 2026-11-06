import { PASSWORD_MAX_LENGTH, PASSWORD_MIN_LENGTH, passwordChecks } from '../lib/password'
import { Icon } from './Icon'

export function PasswordRuleHint({ value, id }: { value: string; id?: string }) {
  const checks = passwordChecks(value)
  return (
    <div className="password-rules" id={id} aria-live="polite">
      <span className={`password-rules__item${checks.length ? ' is-met' : ''}`}>
        <Icon name={checks.length ? 'check' : 'dot'} size={12} />
        长度 {PASSWORD_MIN_LENGTH}–{PASSWORD_MAX_LENGTH} 位
      </span>
      <span className={`password-rules__item${checks.letter ? ' is-met' : ''}`}>
        <Icon name={checks.letter ? 'check' : 'dot'} size={12} />
        含字母
      </span>
      <span className={`password-rules__item${checks.digit ? ' is-met' : ''}`}>
        <Icon name={checks.digit ? 'check' : 'dot'} size={12} />
        含数字
      </span>
    </div>
  )
}
