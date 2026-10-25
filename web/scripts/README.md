# Detection integration runner

This P2-owned runner sends labeled, externally stored audio through the real
`POST /api/detect` route and then applies the production frontend `AlertPolicy`.
It does not generate detections, modify the backend, or store audio in the repo.

Every input must already match production: exactly 48,000 samples of 16 kHz,
mono, 16-bit PCM WAV. The runner rejects silence and reports the measured peak
dBFS sent to the API. Copy `detection-manifest.example.json` outside the repo,
replace its paths and document whether each condition is a real recording or a
simulation. Keep licensed datasets in ignored or temporary storage.

Run a local backend, then:

```sh
npm run evaluate:detection -- /absolute/path/manifest.json \
  http://127.0.0.1:8000 1100 > /absolute/path/results.json
```

Use an interval of at least 10,100 ms when measuring unknown-description behavior
so the backend's describe limit does not suppress cases. A shorter interval is
appropriate for expected built-ins but will record real rate-limit/grouping
behavior. Each response, confidence supplied by the API, frontend admission, and
enabled built-in list is written as JSON. Misses remain misses; the command does
not change expected values to make a run pass.

The runner does not prove physical distance, microphone capture, reverberation or
room-noise performance unless the manifest uses recordings made under those
conditions. Attenuating or mixing a recording must be labeled as simulated in the
manifest; prepare those WAV files without normalization so reported amplitudes
remain meaningful.
