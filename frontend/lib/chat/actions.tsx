export const maxDuration = 300;

import { createAI, createStreamableUI, getMutableAIState, getAIState, createStreamableValue } from 'ai/rsc'
import { nanoid } from '@/lib/utils'
import { saveChat, appendClientInfo } from '@/app/actions'
import { Chat } from '@/lib/types'
import { auth } from '@/auth'
import { getClientInfo } from '@/lib/utils/client-info'
import { BaseMessage, HumanMessage, ToolMessage } from "@langchain/core/messages";
import { DoneMarker } from '@/components/done-marker'

import { 
	render_tool_call_event, 
	render_tool_response_event, 
	render_user_message, 
	render_bot_stream, render_separator, 
	render_event
} from '@/lib/chat/render'

import { Separator } from '@/components/ui/separator'

import { RemoteRunnable } from "@langchain/core/runnables/remote";
const remoteChain = new RemoteRunnable({
	url: process.env.LANGSERVE_URL || "http://localhost:8080/sciscigpt",
	options: { timeout: 3600000 } // 60 minutes
});


export async function submitUserMessage(
	content: string, 
	fileList: any[] = [], 
	selectedModelId: string = 'claude-opus-4.8',
	userApiKey?: string
) {
	'use server'

	const session = await auth()
	const aiState = getMutableAIState<typeof AI>()
	if (aiState.get().title === undefined) {
		aiState.update({ ...aiState.get(), title: content.substring(0, 100) ?? "Test" })
	}
	
	const model_name = selectedModelId ?? 'claude-opus-4.8'
	
	const session_id = aiState.get().chatId
	const db_name = "SciSciNet_US_V4"

	const metadata = {
		format: "events",
		session_id: session_id,
		db_name: db_name,
		model_name: model_name,
		api_key: userApiKey ?? undefined
	}
	
	const human_message = new HumanMessage({ content: [
		{ type: 'text', text: content }, 
		...fileList.map(file => ({ type: 'image_url', image_url: { url: file } }))
	] });

	const human_event = {
		event: "on_custom_event", name: "user_input",
		data: JSON.stringify({ messages: [ human_message.toJSON() ], current: "user_input", next: "node_research_manager" })
	}
	
	const clientInfo = await getClientInfo()

	let textStream: undefined | ReturnType<typeof createStreamableValue<string>>
	let temp_node: undefined | React.ReactNode

	const streamableUI = createStreamableUI();
	
	(async () => {
		try {
			if (aiState.get().messages.length > 1) {
				streamableUI.append(<Separator className="my-4" weight={0.0}/>);
			}
			streamableUI.append(render_user_message(human_message));

			aiState.update({ ...aiState.get(), messages: [ ...aiState.get().messages, JSON.stringify(human_event) ] });

			const metadata_str = JSON.stringify(metadata, null, 4)
			const messages_str = JSON.stringify(aiState.get().messages, null, 4)
			const eventStream = remoteChain.streamEvents(
				{ messages_str: messages_str, metadata_str: metadata_str }, { version: "v2" }); 

			for await (const event of eventStream) {
				// console.log(event)
				const metadata = event.metadata;
				
				if (event.event === "on_chat_model_stream" || event.event === "on_llm_stream") {
					const delta = event.data.chunk?.content?.[0]?.text ?? event.data.chunk?.content ?? '';

					if (delta !== undefined && delta !== "" && typeof delta === 'string') {
						if (textStream === undefined) {
							textStream = createStreamableValue<string>("");
							temp_node = render_bot_stream(textStream.value, metadata);
							streamableUI.append(render_separator("on_chat_model_end"));
							streamableUI.append(temp_node);
						} 
						textStream.update(delta);
					}
				} else if (textStream !== undefined) {
					textStream.done();
					textStream = undefined;
				}

				if (event.event === "on_tool_start") {
					temp_node = render_tool_call_event(event)
					streamableUI.append(render_separator(event.event));
					streamableUI.append(temp_node);
				}

				if (event.event === "on_tool_end") {
					temp_node = render_tool_response_event(event)
					streamableUI.append(render_separator(event.event));
					streamableUI.append(temp_node);
				}

				if (event.event === "on_custom_event") {
					aiState.update({ ...aiState.get(), messages: [ ...aiState.get().messages, JSON.stringify(event) ] });
				}
			}

		} catch (e: any) {
			console.error(e)
			temp_node = "An error occurred. Please try again.\n\n" + e.toString();
			streamableUI.append(render_separator('on_chat_model_end'));
			streamableUI.append(temp_node);
		} 

		
		try { aiState.done(aiState.get()) } catch (e: any) { console.error(e) }
		try { if (textStream !== undefined) { textStream.done() } } catch (e: any) { console.error(e) }
		try {
			streamableUI.done(<DoneMarker />)
		} catch (e: any) { console.error(e) }

	})()

	await appendClientInfo(session_id, clientInfo)
	
	return {
		id: nanoid(),
		display: streamableUI.value
	}
}


export type AIState = {
	chatId: string
	messages: any[]
	title?: string
}

export type UIState = {
	id: string
	display: React.ReactNode
	type: string
}[]

export const AI = createAI<AIState, UIState>({
	actions: { submitUserMessage },
	initialUIState: [],
	initialAIState: { chatId: nanoid(), messages: [] },
	onGetUIState: async () => { 
		'use server'
		const session = await auth()

		if (session && session.user) {
			const aiState = getAIState() as Chat

			if (aiState) {
				const uiState = getUIStateFromAIState(aiState)
				return uiState
			}
		} else {
			return undefined
		}
	},
	onSetAIState: async ({ state }: { state: AIState }) => {
		'use server'

		const session = await auth()

		if (session && session.user) {

			const { chatId, messages, title } = state

			const createdAt = new Date()
			const userId = session.user.id as string
			const path = `/chat/${chatId}`
			
			const chat: Chat = {
				id: chatId,
				title: title ?? "Test",
				userId,
				createdAt,
				messages,
				path,
				status: 'active'
			}

			await saveChat(chat)

		} else {
			return
		}
	}
})


export const getUIStateFromAIState = (aiState: any) => {
	return aiState.messages
		.map((event: any, index: any) => {
			const data = JSON.parse(JSON.parse(event).data);
			
			let node;
			try {
				node = render_event(data);
			} catch (error) {
				node = null;
			}

			return {
				id: `${aiState.chatId}-${index}`,
				display: node,
				type: data.name
			}
		})
}
