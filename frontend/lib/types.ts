import { CoreMessage } from 'ai'

export type Message = CoreMessage & {
  id: string
}

export interface Chat extends Record<string, any> {
  id: string
  title: string
  createdAt: Date
  userId: string
  path: string
  messages: any[]
  sharePath?: string
  clientInfoHistory?: Record<string, string>[]
  status?: 'active' | 'deleted' | 'archived'
}

export type ServerActionResult<Result> = Promise<
  | Result
  | {
      error: string
    }
>

export interface Session {
  user: {
    id: string
    email: string
  }
}

export interface AuthResult {
  type: string
  message: string
}

export interface User extends Record<string, any> {
  id: string
  email: string
  password: string
  salt: string
  emailVerified?: boolean | string
  verificationCode?: string
  verificationExpiresAt?: number | string
  resetCode?: string
  resetCodeExpiresAt?: number | string
}

export interface AccessInfo {
  hasAnthropicKey: boolean
  anthropicKeyLast4?: string
  anthropicKeyMasked?: string
  limitsEnabled: boolean
  limit: number
  limitPeriod: 'day' | 'week' | 'month'
  usageCount: number
  emailVerified?: boolean
}

export interface SettingsSnapshot extends AccessInfo {
  email: string
}
