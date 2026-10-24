import StreamText from './StreamText.jsx';

/** Streams the active situation's one-line story at the top of the map. */
export default function Narration({ situation }) {
  if (!situation) return (
    <div className="narration glass idle" data-tour="narration">
      <small>WELCOME</small>
      <StreamText text="Pick a situation on the left. Watch the city, then help Dana respond." />
    </div>
  );
  return (
    <div className={`narration glass ${situation.running ? 'running' : ''}`} data-tour="narration">
      <small>{situation.title.toUpperCase()}</small>
      <StreamText key={situation.id} text={situation.narration} />
      {situation.running && <div className="progress"><i /></div>}
    </div>
  );
}
