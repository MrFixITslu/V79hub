import fs from 'node:fs';const actual=Date.now.bind(Date);Date.now=()=>actual()+Number(fs.readFileSync('/tmp/v79-test-clock','utf8'));
