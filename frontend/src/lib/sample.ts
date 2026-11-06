export const SAMPLE_CSV = `Device ID,Product Type,Air temperature [K],Process temperature [K],Rotational speed [rpm],Torque [Nm],Tool wear [min]
3号机,M,298.1,308.6,1551,42.8,0
5号机,H,297.5,306.2,1600,48.0,80
7号机,L,300.2,309.1,1320,38.5,145
9号机,M,299.3,307.8,1480,44.2,96
12号机,H,301.4,310.2,1710,52.6,24
14号机,M,296.8,304.9,1220,28.4,210
16号机,L,298.7,307.1,1390,36.9,132
18号机,M,300.1,308.9,1650,49.3,64
21号机,H,302.2,311.4,1790,56.1,12
23号机,L,297.2,305.6,1260,31.7,178
25号机,M,299.8,308.3,1520,41.6,88
28号机,H,300.9,309.6,1680,50.2,42
`

export function sampleCsvFile() {
  return new File([SAMPLE_CSV], '示例巡检_12行.csv', { type: 'text/csv' })
}
