import {useCallback, useEffect, useRef, useState} from 'react';
import type {Recognition} from '../lib/types';
import {spokenWord} from '../lib/state';
import {Icon} from './Icons';

const EDGES = [[0,1],[1,2],[2,3],[3,4],[0,5],[5,6],[6,7],[7,8],[5,9],[9,10],[10,11],[11,12],[9,13],[13,14],[14,15],[15,16],[13,17],[0,17],[17,18],[18,19],[19,20]];
const SUPPORTED_WORDS = ['hello', 'thankyou', 'yes', 'no', 'now', 'please', 'tomorrow', 'wait'];

export function CameraPanel({onWords, onComposing, enabled}: {onWords: (text: string) => void; onComposing?: (value: boolean) => void; enabled: boolean}) {
  const video = useRef<HTMLVideoElement>(null);
  const canvas = useRef<HTMLCanvasElement>(null);
  const worker = useRef<Worker | null>(null);
  const stream = useRef<MediaStream | null>(null);
  const animation = useRef(0);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const initialization = useRef<ReturnType<typeof setTimeout> | null>(null);
  const generation = useRef(0);
  const frames = useRef<Float32Array[]>([]);
  const recording = useRef(false);
  const busy = useRef(false);
  const [open, setOpen] = useState(false);
  const [ready, setReady] = useState(false);
  const [loading, setLoading] = useState(false);
  const [capturing, setCapturing] = useState(false);
  const [reading, setReading] = useState(false);
  const [quality, setQuality] = useState({shoulders: false, hands: 0});
  const [words, setWords] = useState<string[]>([]);
  const [result, setResult] = useState<Recognition | null>(null);
  const [problem, setProblem] = useState('');
  const [showWords, setShowWords] = useState(false);
  const choices = result?.kind === 'chip' ? [] : (result?.suggestions ?? (result?.kind === 'candidate' && result.gloss ? [result.gloss] : [])).filter(word => SUPPORTED_WORDS.includes(word)).slice(0, 3);
  const addWord = (word: string) => {
    if (!enabled || !SUPPORTED_WORDS.includes(word)) return;
    setWords(old => old.at(-1) === word ? old : [...old, word].slice(0, 8));
    setResult(null); onComposing?.(true);
  };

  const stop = useCallback(() => {
    generation.current++;
    cancelAnimationFrame(animation.current); if (timer.current) clearTimeout(timer.current);
    if (initialization.current) clearTimeout(initialization.current);
    stream.current?.getTracks().forEach(track => track.stop()); stream.current = null;
    worker.current?.terminate(); worker.current = null;
    recording.current = false; busy.current = false;
    frames.current = [];
    setOpen(false); setReady(false); setLoading(false); setCapturing(false);
  }, []);
  useEffect(() => stop, [stop]);

  const finish = useCallback(async () => {
    if (!recording.current) return;
    recording.current = false; setCapturing(false); if (timer.current) clearTimeout(timer.current);
    if (frames.current.length < 6) { setProblem('Record one complete sign, then finish.'); return; }
    const input = new Float32Array(frames.current.length * 543 * 3);
    frames.current.forEach((frame, i) => input.set(frame, i * 543 * 3));
    frames.current = []; setReading(true); setProblem('');
    const run = generation.current;
    try {
      const response = await fetch('/web/recognize', {method: 'POST', credentials: 'same-origin', headers: {'Content-Type': 'application/octet-stream'}, body: input.buffer});
      if (!response.ok) throw new Error(response.status === 401 ? 'Unlock the call desk to use signing.' : 'Signing is unavailable right now. You can still type.');
      const match = await response.json() as Recognition;
      if (run !== generation.current) return;
      setResult(match);
      if (match.kind === 'chip' && match.gloss && SUPPORTED_WORDS.includes(match.gloss)) setWords(old => old.at(-1) === match.gloss ? old : [...old, match.gloss!].slice(0, 8));
    } catch (error) { if (run === generation.current) setProblem(error instanceof Error ? error.message : 'That sign couldn’t be read. Please try again.'); }
    finally { setReading(false); }
  }, []);

  const start = async () => {
    if (!enabled) { setProblem('Unlock the call desk to use webcam signing.'); return; }
    const run = ++generation.current;
    setProblem(''); setOpen(true); setLoading(true);
    initialization.current = setTimeout(() => {
      if (run !== generation.current) return;
      stop(); onComposing?.(false);
      setProblem('The camera tracker took too long to start. Try enabling the camera again, or type your reply.');
    }, 45000);
    try {
      const media = await navigator.mediaDevices.getUserMedia({video: {facingMode: 'user', width: {ideal: 960}, height: {ideal: 720}}, audio: false});
      if (run !== generation.current) { media.getTracks().forEach(track => track.stop()); return; }
      stream.current = media;
      if (!video.current) { media.getTracks().forEach(track => track.stop()); return; }
      video.current.srcObject = media;
      // A playback promise can remain pending after resizing/backgrounding a tab.
      // Model initialization is independent; frame capture checks readyState below.
      void video.current.play().catch(() => {
        if (run !== generation.current) return;
        stop(); setProblem('The camera preview couldn’t play. Enable the camera again.');
      });
      const model = new Worker(new URL('../lib/landmark.worker.ts', import.meta.url), {type: 'module'});
      worker.current = model;
      let lastFrame = 0;
      const loop = (timestamp: number) => {
        animation.current = requestAnimationFrame(loop);
        const element = video.current;
        if (!element || element.readyState < 2 || busy.current || timestamp - lastFrame < 1000 / 12) return;
        lastFrame = timestamp; busy.current = true;
        void createImageBitmap(element).then(bitmap => model.postMessage({type: 'frame', bitmap, timestamp}, [bitmap])).catch(() => { busy.current = false; });
      };
      model.onmessage = ({data}) => {
        if (run !== generation.current) return;
        if (data.type === 'ready') { if (initialization.current) clearTimeout(initialization.current); setReady(true); setLoading(false); animation.current = requestAnimationFrame(loop); }
        else if (data.type === 'error') { stop(); setProblem(data.message); }
        else {
          busy.current = false;
          if (data.type !== 'frame') return;
          const values = data.values as Float32Array;
          setQuality({shoulders: data.shoulders, hands: data.hands});
          if (recording.current && frames.current.length < 64) frames.current.push(values.slice());
          const context = canvas.current?.getContext('2d');
          if (!context || !canvas.current || !video.current) return;
          const width = canvas.current.width = video.current.videoWidth;
          const height = canvas.current.height = video.current.videoHeight;
          context.clearRect(0, 0, width, height); context.strokeStyle = '#d9fbe6'; context.lineWidth = 3;
          for (const offset of [468, 522]) {
            for (const [a, b] of EDGES) {
              const x = values[(offset + a) * 3], y = values[(offset + a) * 3 + 1];
              const bx = values[(offset + b) * 3], by = values[(offset + b) * 3 + 1];
              if (![x, y, bx, by].every(Number.isFinite)) continue;
              context.beginPath(); context.moveTo(x * width, y * height); context.lineTo(bx * width, by * height); context.stroke();
            }
          }
        }
      };
      model.onerror = () => { setProblem('The camera tracker stopped. Close it and try again.'); setLoading(false); busy.current = false; };
      model.postMessage({type: 'init'});
    } catch (error) {
      stop();
      setProblem(error instanceof DOMException && error.name === 'NotAllowedError' ? 'Camera access is off. Allow it in your browser’s site settings, then try again.' : 'Couldn’t open the camera. Check it is connected and not in use.');
    }
  };

  return <section className="camera-panel" aria-labelledby="sign-heading">
    <div className="panel-heading"><h2 id="sign-heading"><Icon name="hand" /> Say it with a sign</h2><span className="tag">ASL preview</span></div>
    <p className="secondary">One sign at a time. Review your words before using them.</p>
    <button className="text-button signing-word-toggle" aria-expanded={showWords} onClick={() => setShowWords(old => !old)}>{showWords ? 'Hide words' : 'All 8 words · tap to choose'}</button>
    {showWords && <div className="signing-word-palette" aria-label="Supported signing words">{SUPPORTED_WORDS.map(word => <button key={word} disabled={!enabled || words.length >= 8} onClick={() => addWord(word)}>{spokenWord(word)}</button>)}</div>}
    <div className={`camera-frame ${open ? 'is-open' : ''}`}>
      <video ref={video} playsInline muted aria-label="Mirrored webcam preview" />
      <canvas ref={canvas} aria-hidden="true" />
      {!open && <div className="camera-empty"><span className="camera-glyph"><Icon name="hand" size={38} /></span><strong>A little space for your hands.</strong><p>Keep your face, shoulders and hands in view.</p><button className="button button-outline" onClick={() => void start()}><Icon name="camera" /> Enable camera</button></div>}
      {open && <><button className="icon-button camera-close" aria-label="Turn off camera" onClick={() => { stop(); onComposing?.(false); }}><Icon name="close" /></button><span className={`camera-status ${capturing ? 'recording' : ''}`}>{loading ? 'Loading tracker…' : capturing ? 'Recording one sign…' : quality.shoulders ? `${quality.hands} ${quality.hands === 1 ? 'hand' : 'hands'} in view` : 'Move back to show your shoulders'}</span></>}
    </div>
    {open && <div className="camera-actions"><button className={`button ${capturing ? 'button-dark' : 'button-purple'}`} disabled={!ready || reading || words.length >= 8} onClick={() => {
      if (recording.current) { void finish(); return; }
      frames.current = []; recording.current = true; setCapturing(true); setResult(null); setProblem(''); onComposing?.(true);
      timer.current = setTimeout(() => void finish(), 4000);
    }}><Icon name={capturing ? 'check' : 'hand'} />{reading ? 'Reading sign…' : capturing ? 'Finish sign' : 'Record one sign'}</button><span className="hint">Up to 4 seconds</span></div>}
    <div aria-live="polite">
      {choices.length > 0 && <div className="signing-choices"><div><span>Choose a word</span><button className="text-button" onClick={() => setResult(null)}>Dismiss</button></div><div className="signing-word-palette" aria-label="Sign suggestions">{choices.map(word => <button key={word} disabled={words.length >= 8} onClick={() => addWord(word)}>{spokenWord(word)}</button>)}</div></div>}
      {result?.kind === 'unsure' && choices.length === 0 && <p className="recognition-message">{result.reason} Try again, or choose from All 8 words.</p>}
      {problem && <p className="error-message" role="alert">{problem}</p>}
    </div>
    {words.length > 0 && <div className="word-review"><div className="word-chips">{words.map((word, i) => <button key={`${i}-${word}`} onClick={() => setWords(old => old.filter((_, index) => i !== index))} aria-label={`Remove ${spokenWord(word)}`}>{spokenWord(word)}<Icon name="close" size={12} /></button>)}</div><button className="text-button" onClick={() => { onWords(words.map(spokenWord).join(' ')); setWords([]); setResult(null); }}>Edit sentence <Icon name="arrow" size={16} /></button><p className="hint">Review and finish your sentence before Send. Nothing is spoken here.</p></div>}
    <p className="privacy-note"><Icon name="shield" size={15} /><span>Video stays in your browser. Landmark coordinates go to Ishara for recognition and aren’t saved. Experimental, 8-word ASL vocabulary.</span></p>
  </section>;
}
