import { StreamEvent } from '@langchain/core/dist/tracers/event_stream';
import { BotCard, UserCard, UserMessage, BotMessage, SystemMessage, SpinnerMessage } from '@/lib/chat/components/message'
import { ImageFromSrc } from '@/lib/chat/components/image-loader'
import ImageClientWrapper from '@/lib/chat/components/image-loader'
import { IconCSSI } from '@/components/ui/icons'
import CSVDownLoadClientWrapper from '@/lib/chat/components/csv-downloader'
import { Separator } from '@/components/ui/separator';
import {HumanMessage} from "@langchain/core/messages"
import { Messages } from 'openai/resources/beta/threads/messages';
import { process_xml } from '@/lib/chat/components/xml'


function format_name(name: string) {
	return name.replace("node_", "").split('_').map((word: string) => word.charAt(0).toUpperCase() + word.slice(1)).join('');
}

export function render_tool_call_event(event: StreamEvent) {
	const name = event.name
	const args = typeof event.data.input === 'string' ? JSON.parse(event.data.input) : event.data.input
	const textResponse = __render_tool_call__(name, args)
	return (<div> {textResponse} </div>)
}

function __render_tool_call__(name: string, args: any) {
	var content = ''
	var header = 'header'

	delete args.state

	if (name.endsWith('specialist')) {
		const task = args.task.split('\n').map((line: string) => `  ${line}`).join('\n')
		content = `**Delegate task to ${name}:** \n\n${task}`
		header = "Task"
		return <BotMessage content={ content } header={header}/>
	} else if (name === 'search_literature') {
		header = "Searching literature..."
		content = `<search>${args.query}</search>`
		return <BotMessage content={ content } header={header}/>
	} else if (name === 'sql_query' || name === 'neo4j_query' ) {
		content = '```sql\n' + args.query + '\n```'
		// content = args.query
		header = "SQL"
		return <BotMessage content={ content } header={header}/>
	} else if (name === 'python') {
		content = '```python\n' + args.query + '\n```'
		header = "Python"
		return <BotMessage content={ content } header={header}/>
	} else if (name === 'julia') {
		content = '```julia\n' + args.query + '\n```'
		header = "Julia"
		return <BotMessage content={ content } header={header}/>
	} else if (name === 'r') {
		content = '```r\n' + args.query + '\n```'
		header = "R"
		return <BotMessage content={ content } header={header}/>
	} else {
		content = `Invoking tool: \`${name}\` with inputs: \`${JSON.stringify(args)}\``
		return <BotMessage content={ content } header={header}/>
	}
}

export function render_tool_response_event(event: StreamEvent) {
	const output = typeof event.data.output === 'string' ? JSON.parse(event.data.output) : event.data.output;
	return __render_tool_response__(event.name, output)
}

export function render_tool_message(node_name: string, message: any) {
	const content = JSON.parse(message.content[0].text)
	return __render_tool_response__(node_name, content);
}

function __render_tool_response__ (name: string, result: any) {
	const text = result.response !== undefined ? result.response : ''
	const images = result.images !== undefined && result.images.length > 0 ? result.images: []

	const files = []
	if (result.file !== undefined) {
		files.push({
			name: result.file.split('/').pop(),
			id: result.file.split('/').pop().split('.')[0],
			download_link: result.file.replace(process.env.LOCAL_STORAGE_PATH, "https://storage.googleapis.com/sciscigpt-fs/"),
			mimeType: result.file.split('.').pop()
		})
	}
	if (result.files !== undefined) {
		files.push(...result.files)
	}
	
	const textResponse = __render_tool_response_text__(name, text)
	const imagesResponse = images.length > 0 ? <ImageClientWrapper images={images} /> : null
	const filesResponse = files.length > 0 ? files.map((file: any, index: number) => (
		<CSVDownLoadClientWrapper key={index} src={file.download_link} name={file.name} />
	)) : null

	return <div> {textResponse} {imagesResponse} {filesResponse} </div>
}


function __render_tool_response_text__ (name: string, text: string) {
	var content = '';
	var header = ''
	if (name === 'sql_list_table') {	
		content = '```\n' + text + '\n```'
		header = "sql_list_table"
	} else if (name === 'sql_get_schema') {	
		content = '```sql\n' + text + '\n```'
		header = "sql_get_schema"
	} else if (name === 'sql_query') {
		content = text ? "```output\n" + text + "\n```" : ""
		header = "sql_query"
	} else if (name === 'search_name') {
		content = '```output\n' + text + '\n```'
		header = "search_name"
	} else if (name === 'python') {
		content = text ? "```python\n" + text + "\n```" : ""
		header = "python"
	}else if (name === 'r') {
		content = text ? "```r\n" + text + "\n```" : ""
		header = "r"
	} else if (name === 'julia') {
		content = text ? "```julia\n" + text + "\n```" : ""
		header = "julia" } 
	else {
		content = text
	}

	if (content === '') {
		return null
	} 

	return <BotMessage content={content} header={header} icon_invisible={true}/>
}

export function render_user_message(message: any) {
	const content = message.content
	const image_nodes = content.filter((message: any) => message.type === 'image_url').map((message: any, index: any) => {
		const url = message.image_url.url ? message.image_url.url : message.image_url
		return <ImageFromSrc imageBase64={url} key={index}/>
	});

	const text_nodes = content.filter((message: any) => message.type === 'text').map((message: any, index: any) => {
		return message.text
	});

	return (
		<UserCard>
			{ text_nodes }
			{ image_nodes }
		</UserCard>
	)
}

export function render_bot_stream(stream: any, metadata: any={}) {
	const name = format_name(metadata?.langgraph_node)
	return <BotMessage content={stream} name={name} header={name} icon_invisible={false} icon={<IconCSSI/>}/>;
}

export function render_ai_message(message: any, name: string) {
	const text_ = typeof message.content === 'string' ? message.content : message.content[0]?.text
	const text = process_xml(text_)
	
	const text_node = <BotMessage content={text} name={name} header={name} icon_invisible={false} icon={<IconCSSI/>}/>

	if (text_node === undefined || text.length === 0) {
		return null
	}

	const tool_calls_node = message.tool_calls.map((tool_call: any) => {
		return __render_tool_call__(tool_call.name, tool_call.args)
	})

	if (text_node === null && message.tool_calls.length == 0) {
		return null
	} else {
		return <div> {text_node} {render_separator('on_tool_start')} {tool_calls_node} </div>
	}
}


export function render_separator(
	type: 'on_user_input' | 'on_chat_model_end' | 'on_tool_start' | 'on_tool_end' | string
) {
	if (type === 'on_user_input' || type === 'on_chat_model_end') {
		return <Separator className="my-4" weight={0.0} />;
	} else if (type === 'on_tool_start') {
		return <Separator className="my-4" weight={0.0} />;
	} else if (type === 'on_tool_end') {
		return <Separator className="my-4" weight={0.0} />;
	} else 
	
	
	if (type === 'call_specialist' || type === 'call_research_manager' || type === 'call_evaluation') {
		return <Separator className="my-4" weight={0.0} />;
	} else
	if (type === 'call_toolset') {
		return <Separator className="my-4" weight={0.0} />;
	}
	return null;
}


export function render_event(event: any) {
	const {messages = [], current, next, name = ""} = event

	if (messages.length === 0) {
		return null
	}

	if (current === "user_input") {
		const message = new HumanMessage(messages[0].kwargs)
		return render_user_message(message)
	}

	// Compaction summaries are stored for replay but never displayed.
	if (name === "call_compactor") {
		return null
	}

	if (name === "call_research_manager") {
		return render_ai_message(messages[0].kwargs, format_name(current))
	}

	if (name === "call_specialist") {
		return render_ai_message(messages[0].kwargs, format_name(current))
	}

	if (name === "call_evaluation") {
		return render_ai_message(messages[0].kwargs, format_name(current))
	}

	if (name === "call_toolset") {
		const content = JSON.parse(messages[0].kwargs.content[0].text)
		return __render_tool_response__(current, content)
	}

	if (name === "limit_notice") {
		return render_ai_message(messages[0].kwargs, "Usage limit")
	}
}
