
export const streamChat = async (
  baseUrl: string,
  apiKey: string,
  payload: any,
  onChunk: (chunk: string) => void
) => {
  try {
    const url = baseUrl.replace(/\/$/, '');
    const response = await fetch(`${url}/chat`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-API-Key': apiKey,
      },
      mode: 'cors',
      body: JSON.stringify(payload),
    });

    if (!response.ok) {
      const err = await response.text();
      if (response.status === 403) throw new Error("Secret Key Mismatch: Check 'home-link-secret' in Settings.");
      if (response.status === 404) throw new Error("Bridge Port Error: Check if main.py is running on port 6969.");
      throw new Error(err || `Bridge returned ${response.status}`);
    }

    const reader = response.body?.getReader();
    if (!reader) throw new Error('Empty stream response');

    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      
      const lines = buffer.split('\n');
      buffer = lines.pop() || '';

      for (const line of lines) {
        const trimmed = line.trim();
        if (!trimmed) continue;

        if (trimmed.startsWith('data: ')) {
          const data = trimmed.slice(6).trim();
          if (data === '[DONE]') break;
          
          try {
            const parsed = JSON.parse(data);
            if (parsed.error) throw new Error(parsed.error);
            const chunk = parsed.choices?.[0]?.delta?.content || '';
            if (chunk) onChunk(chunk);
          } catch (e) {
            // Silently handle partial JSON chunks if they happen during streaming
            console.debug('Skip partial chunk');
          }
        }
      }
    }
  } catch (error: any) {
    console.error('streamChat error:', error);
    
    if (error.message === 'Failed to fetch') {
      const isHttps = window.location.protocol === 'https:';
      if (isHttps && !baseUrl.includes('localhost')) {
        throw new Error("HTTPS Mixed Content Block: Ensure you allowed 'Insecure Content' for this IP address in your browser site settings.");
      }
      throw new Error("Bridge Unreachable: Ensure main.py is running on your Alienware and you are using the correct IP/Port (6969).");
    }
    throw error;
  }
};
