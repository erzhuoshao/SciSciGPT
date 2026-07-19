import * as React from 'react'

import { shareChat } from '@/app/actions'
import { Button } from '@/components/ui/button'
import { PromptForm } from '@/components/prompt-form'
import { IconShare } from '@/components/ui/icons'
import { ChatShareDialog } from '@/components/chat-share-dialog'
import { useAIState, useUIState } from 'ai/rsc'
import { AccessInfo } from '@/lib/types'

export interface ChatPanelProps {
	id?: string
	title?: string
	input: string
	setInput: (value: string) => void
	isAtBottom: boolean
	scrollToBottom: () => void
	session?: any
	accessInfo?: AccessInfo
}

export function ChatPanel({
	id,
	title,
	input,
	setInput,
	isAtBottom,
	scrollToBottom,
	session,
	accessInfo
}: ChatPanelProps) {
	const [aiState] = useAIState()
	const [messages] = useUIState()
	const [shareDialogOpen, setShareDialogOpen] = React.useState(false)
	const limitPeriodLabel =
		accessInfo?.limitPeriod === 'week'
			? 'per week'
			: accessInfo?.limitPeriod === 'month'
				? 'per month'
				: 'per day'
	const remainingWindowLabel =
		accessInfo?.limitPeriod === 'week'
			? 'this week'
			: accessInfo?.limitPeriod === 'month'
				? 'this month'
				: 'today'
	const remaining =
		typeof accessInfo?.usageCount === 'number'
			? Math.max(0, (accessInfo?.limit ?? 0) - accessInfo.usageCount)
			: undefined

	const exampleMessages = [
		{
			heading: 'Collaboration Network',
			subheading: 'Ivy League universities',
			message: `Generate a network for collaborations among Ivy League Universities between 2000 and 2020. Optimize its colors and annotations.`
		},
		{
			heading: 'AI Trends',
			subheading: 'Trending research institutions in AI',
			message: 'Which research institutions are trending in AI over time? X = time, Y = # AI publications, Hue = top institutions.'
		},
		{
			heading: 'Valuable Papers',
			subheading: 'citation + disruption + novelty',
			message: `Who has published papers with the most citations + highest disruption + highest novelty?`
		},
		{
			heading: 'Nanotechnology',
			subheading: `5 leading research institutions`,
			message: `List the five leading research institutions in nanotechnology, their total citations for nanotechnology papers, and representative publications.`
		}
	]

	return (
		// <div className="fixed inset-x-0 bottom-0 w-full bg-gradient-to-b duration-300 ease-in-out animate-in dark:from-background/10 dark:from-10% dark:to-background/80 peer-[[data-state=open]]:group-[]:lg:pl-[250px] peer-[[data-state=open]]:group-[]:xl:pl-[300px]">
		<div className="fixed inset-x-0 bottom-0 w-full bg-gradient-to-b peer-[[data-state=open]]:group-[]:xl:pl-[300px]">
			<div className="mx-auto sm:max-w-4xl sm:px-4">
				<div className="mb-4 grid grid-cols-2 gap-2 px-4 sm:px-0">
					{messages.length === 0 &&
						exampleMessages.map((example, index) => (
							<div
								key={example.heading}
								className={`cursor-pointer rounded-lg border bg-white p-4 hover:bg-zinc-50 dark:bg-zinc-950 dark:hover:bg-zinc-900 ${
									index > 1 && 'hidden md:block'
								}`}
								onClick={() => {
									setInput(example.message)
								}}
							>
								<div className="text-sm font-semibold">{example.heading}</div>
								<div className="text-sm text-zinc-600">
									{example.subheading}
								</div>
							</div>
						))}
				</div>

				{messages?.length >= 2 ? (
					<div className="flex h-12 items-center justify-center">
						<div className="flex space-x-2">
							{id && title ? (
								<>
									<Button
										variant="outline"
										onClick={() => setShareDialogOpen(true)}
									>
										<IconShare className="mr-2" />
										Share
									</Button>
									<ChatShareDialog
										open={shareDialogOpen}
										onOpenChange={setShareDialogOpen}
										onCopy={() => setShareDialogOpen(false)}
										shareChat={shareChat}
										chat={{
											id,
											title,
											messages: aiState.messages
										}}
									/>
								</>
							) : null}
						</div>
					</div>
				) : null}

				<div className="space-y-4 border-t bg-background px-4 py-2 shadow-lg sm:rounded-t-xl sm:border md:py-4">
					{accessInfo?.limitsEnabled && !accessInfo?.hasAnthropicKey && (
						<div className="text-xs text-muted-foreground px-1">
							Free tier: {accessInfo?.limit ?? 5} questions {limitPeriodLabel}.{' '}
							{typeof remaining === 'number' && (
								<>{remaining} left {remainingWindowLabel}. </>
							)}
							Add your Anthropic API key in{' '}
							<a href="/settings" className="underline font-semibold">
								Settings
							</a>{' '}
							to remove limits.
						</div>
					)}
					<PromptForm input={input} setInput={setInput} session={session} />
				</div>
			</div>
		</div>
	)
}
