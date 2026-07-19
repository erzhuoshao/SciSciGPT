from jupyter_client import KernelManager
from queue import Empty
import os, time, uuid, re
from IPython.core.ultratb import FormattedTB
from typing import Dict, Optional
import asyncio

# Shared, versioned figure style (preloaded into every kernel)
STYLE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "figure_style")

class JupyterSandbox:
    def __init__(self, working_dir: str, kernel_name: str=None):
        """Initialize the session manager to handle multiple Jupyter kernels"""
        self.working_dir = working_dir
        self.kernel_name = kernel_name
        self.sessions: Dict[str, Dict] = {}
        self.tb_formatter = FormattedTB(mode='Plain')

    def session_dir(self, session_id: str) -> str:
        """Per-session working directory: <working_dir>/session-<id>."""
        safe = re.sub(r"[^A-Za-z0-9_-]", "_", str(session_id)) or "default"
        return os.path.join(self.working_dir, f"session-{safe}")

    def get_or_create_session(self, session_id: str) -> Dict:
        """
        Get an existing session or create a new one
        
        Parameters:
        session_id (str): Unique identifier for the session
        
        Returns:
        dict: Session information containing kernel manager and client
        """
        if session_id not in self.sessions:
            # Create new kernel and client
            km = KernelManager(kernel_name=self.kernel_name) if self.kernel_name else KernelManager()
            km.start_kernel()
            kc = km.client()
            kc.start_channels()
            # Wait for kernel to be ready
            kc.wait_for_ready()
            
            self.sessions[session_id] = {
                'km': km,
                'kc': kc,
                'last_used': time.time()
            }

            session_dir = self.session_dir(session_id)
            os.makedirs(session_dir, exist_ok=True)

            self.execute_code(
                "%load_ext rpy2.ipython", session_id=session_id, cell_id=str(uuid.uuid4()), timeout=120)
            self.execute_code(
                "from juliacall import Main as jl", session_id=session_id, cell_id=str(uuid.uuid4()), timeout=120)
            self.execute_code(
                f"import os, sys; os.chdir('{session_dir}'); sys.path.insert(0, '{STYLE_DIR}')",
                session_id=session_id, cell_id=str(uuid.uuid4()), timeout=120)
            self.execute_code(
                f"import matplotlib; matplotlib.style.use('{STYLE_DIR}/sciscigpt.mplstyle')",
                session_id=session_id, cell_id=str(uuid.uuid4()), timeout=120)
        else:
            # Update last used timestamp
            self.sessions[session_id]['last_used'] = time.time()

        return self.sessions[session_id]

    def format_traceback(self, traceback_list):
        """
        Convert traceback information to readable plain text format
        
        Parameters:
        traceback_list (list): Original traceback information list
        
        Returns:
        str: Formatted error message
        """
        # Remove ANSI escape sequences
        ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
        cleaned_traceback = [ansi_escape.sub('', line) for line in traceback_list]
        
        return '\n'.join(cleaned_traceback)

    def execute_code(self, code: str, session_id: str, cell_id: str, timeout: int = 120):
        """
        Execute Python code in a specific session and return results
        
        Parameters:
        code (str): Python code to execute
        session_id (str): Session identifier for persistent variables
        timeout (int): Execution timeout in seconds
        
        Returns:
        list: List of output results, each element could be:
            - Text output: {'type': 'text', 'text': content}
            - Image output: {'type': 'image_url', 'image_url': {'url': base64_image}}
            - Error output: {'type': 'text', 'text': error_message}
        """
        session = self.get_or_create_session(session_id)
        kc = session['kc']
        
        msg_id = kc.execute(code)
        outputs = []
        
        start_time = time.time()
        while True:
            try:
                msg = kc.get_iopub_msg(timeout=1)
                msg_type = msg['header']['msg_type']
                content = msg['content']
                
                if msg_type == 'stream':
                    # Text output
                    outputs.append({
                        'type': 'text',
                        'text': content['text']
                    })
                    
                elif msg_type == 'execute_result':
                    # Execution result as text output
                    outputs.append({
                        'type': 'text',
                        'text': str(content['data'].get('text/plain', ''))
                    })
                    
                elif msg_type == 'display_data':
                    # Handle image output
                    if 'image/png' in content['data']:
                        image_data = content['data']['image/png']
                        # Ensure base64 string has correct prefix
                        if not image_data.startswith('data:image/png;base64,'):
                            image_data = 'data:image/png;base64,' + image_data
                        outputs.append({
                            'type': 'image_url',
                            'image_url': {
                                'url': image_data
                            }
                        })
                    elif 'text/plain' in content['data']:
                        outputs.append({
                            'type': 'text',
                            'text': content['data']['text/plain']
                        })
                        
                elif msg_type == 'error':
                    # Error message as text output
                    formatted_error = self.format_traceback(content['traceback'])
                    outputs.append({
                        'type': 'text',
                        'text': formatted_error
                    })
                    
                elif msg_type == 'status' and content['execution_state'] == 'idle':
                    break
                    
            except Empty:
                if time.time() - start_time > timeout:
                    outputs.append({
                        'type': 'text',
                        'text': f'Execution timeout after {timeout} seconds'
                    })
                    break
                continue
        outputs = [o | {'cell_id': cell_id, 'session_id': session_id} for o in outputs]
        return outputs

    def close_session(self, session_id: str):
        """
        Close a specific session and clean up its resources
        
        Parameters:
        session_id (str): Session identifier to close
        """
        if session_id in self.sessions:
            session = self.sessions[session_id]
            session['kc'].stop_channels()
            session['km'].shutdown_kernel()
            del self.sessions[session_id]

    def close_all_sessions(self):
        """Close all active sessions and clean up resources"""
        for session_id in list(self.sessions.keys()):
            self.close_session(session_id)

    def cleanup_inactive_sessions(self, max_idle_time: int = 3600):
        """
        Clean up sessions that have been inactive for longer than max_idle_time
        
        Parameters:
        max_idle_time (int): Maximum idle time in seconds before session cleanup
        """
        current_time = time.time()
        for session_id in list(self.sessions.keys()):
            session = self.sessions[session_id]
            if current_time - session['last_used'] > max_idle_time:
                self.close_session(session_id)