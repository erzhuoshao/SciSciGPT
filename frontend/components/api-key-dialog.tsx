'use client'

import { useEffect, useMemo, useState, useTransition } from 'react'
import Link from 'next/link'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { AccessInfo } from '@/lib/types'
import { useLocalStorage } from '@/lib/hooks/use-local-storage'
import { saveAnthropicApiKey } from '@/app/settings/actions'
import { toast } from 'sonner'

export function ApiKeyDialog({ accessInfo }: { accessInfo?: AccessInfo }) {
  const [apiKey, setApiKey] = useState('')
  const [open, setOpen] = useState(false)
  const [hasLocalKey, setHasLocalKey] = useState(false)
  const [dismissedOn, setDismissedOn] = useLocalStorage<string>(
    'anthropicPromptDismissedAt',
    ''
  )
  const [isPending, startTransition] = useTransition()

  const remaining = useMemo(() => {
    if (!accessInfo) return 0
    return Math.max(0, accessInfo.limit - accessInfo.usageCount)
  }, [accessInfo])

  const limitPeriodLabel = useMemo(() => {
    switch (accessInfo?.limitPeriod) {
      case 'week':
        return { per: 'per week', window: 'this week' }
      case 'month':
        return { per: 'per month', window: 'this month' }
      default:
        return { per: 'per day', window: 'today' }
    }
  }, [accessInfo?.limitPeriod])

  useEffect(() => {
    if (hasLocalKey) {
      setOpen(false)
      return
    }

    if (!accessInfo) {
      return
    }

    if (accessInfo.hasAnthropicKey) {
      setOpen(false)
      return
    }

    const today = new Date().toISOString().slice(0, 10)
    if (dismissedOn !== today) {
      setOpen(true)
    }
  }, [accessInfo, dismissedOn, hasLocalKey])

  const handleOpenChange = (nextOpen: boolean) => {
    if (!nextOpen && !accessInfo?.hasAnthropicKey) {
      const today = new Date().toISOString().slice(0, 10)
      setDismissedOn(today)
    }
    setOpen(nextOpen)
  }

  const handleSaveKey = () => {
    startTransition(async () => {
      const response = await saveAnthropicApiKey(apiKey)
      if (response?.type === 'success') {
        toast.success(response.message)
        setApiKey('')
        setOpen(false)
        setHasLocalKey(true)
        setDismissedOn('')
      } else if (response?.message) {
        toast.error(response.message)
      }
    })
  }

  if (accessInfo?.hasAnthropicKey || !accessInfo?.limitsEnabled) {
    return null
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Bring your Anthropic API key</DialogTitle>
          {accessInfo?.limitsEnabled ? (
            <DialogDescription>
              Add your key to unlock unlimited conversations. Without a key you can
              ask up to {accessInfo?.limit ?? 5} questions {limitPeriodLabel.per}; you have{' '}
              {remaining} left {limitPeriodLabel.window}.
            </DialogDescription>
          ) : (
            <DialogDescription>
              Add your key to unlock unlimited conversations on your own Anthropic account.
            </DialogDescription>
          )}
        </DialogHeader>
        <div className="space-y-3">
          <Input
            type="password"
            placeholder="sk-ant-..."
            value={apiKey}
            onChange={event => setApiKey(event.target.value)}
            disabled={isPending}
          />
          <p className="text-xs text-muted-foreground">
            Your key is stored securely and only used for your account. You can
            update or remove it anytime from the{' '}
            <Link href="/settings" className="font-semibold underline">
              settings page
            </Link>
            .
          </p>
        </div>
        <DialogFooter className="gap-2">
          <Button
            type="button"
            variant="ghost"
            disabled={isPending}
            onClick={() => handleOpenChange(false)}
          >
            Not now
          </Button>
          <Button
            type="button"
            disabled={isPending || !apiKey.trim()}
            onClick={handleSaveKey}
          >
            Save key
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
