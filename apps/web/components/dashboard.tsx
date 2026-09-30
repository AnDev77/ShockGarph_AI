"use client";

import {
  Badge,
  Box,
  Button,
  Flex,
  Grid,
  Heading,
  HStack,
  SimpleGrid,
  Spinner,
  Text,
  VStack,
} from "@chakra-ui/react";
import { useEffect, useMemo, useState } from "react";

type AssetId = "SPY" | "TLT";
type Horizon = "m5" | "m30";
type LoadState = "loading" | "ready" | "error";

interface ResearchResponse {
  status: "ready";
  as_of: string;
  independent_event_count: number;
  finding: string;
  metrics: {
    eligible_events: number;
    comparable_events: number;
    raw_market_brier: number;
    expanding_historical_brier: number;
    mean_brier_difference: number;
    paired_event_bootstrap95: [number, number];
  };
}

interface AnalysisResponse {
  status: "insufficient_data" | "ready" | "exploratory";
  reason?: string;
  independent_event_count: number;
  diagnostic_test_events?: number;
  research_test_events?: number;
  research_required_test_events?: number;
  research_status?: "exploratory" | "insufficient_test_events";
  comparison?: {
    historical_crps: number;
    kalshi_crps: number;
    mean_crps_difference: number;
    paired_event_bootstrap95: [number, number];
  } | null;
}

const assets: Array<{ id: AssetId; name: string; role: string }> = [
  { id: "SPY", name: "미국 주식", role: "성장·위험선호" },
  { id: "TLT", name: "장기 국채", role: "금리 민감도" },
];

const apiBase = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export function Dashboard() {
  const [asset, setAsset] = useState<AssetId>("SPY");
  const [horizon, setHorizon] = useState<Horizon>("m5");
  const [research, setResearch] = useState<ResearchResponse | null>(null);
  const [analysis, setAnalysis] = useState<AnalysisResponse | null>(null);
  const [researchState, setResearchState] = useState<LoadState>("loading");
  const [analysisState, setAnalysisState] = useState<LoadState>("loading");

  useEffect(() => {
    const controller = new AbortController();
    setResearchState("loading");
    fetch(`${apiBase}/v1/research/cpi-probability`, { signal: controller.signal })
      .then(async (response) => {
        if (!response.ok) throw new Error("research unavailable");
        return (await response.json()) as ResearchResponse;
      })
      .then((payload) => {
        setResearch(payload);
        setResearchState("ready");
      })
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === "AbortError") return;
        setResearchState("error");
      });
    return () => controller.abort();
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    setAnalysisState("loading");
    const params = new URLSearchParams({ asset_id: asset, event_category: "CPI", horizon });
    fetch(`${apiBase}/v1/analysis?${params}`, { signal: controller.signal })
      .then(async (response) => {
        if (!response.ok) throw new Error("analysis unavailable");
        return (await response.json()) as AnalysisResponse;
      })
      .then((payload) => {
        setAnalysis(payload);
        setAnalysisState("ready");
      })
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === "AbortError") return;
        setAnalysisState("error");
      });
    return () => controller.abort();
  }, [asset, horizon]);

  const selectedAsset = useMemo(() => assets.find((item) => item.id === asset)!, [asset]);

  return (
    <Box minH="100vh">
      <Box as="header" borderBottom="1px solid" borderColor="rgba(228,231,240,.8)" bg="rgba(255,255,255,.72)" backdropFilter="blur(18px)">
        <Flex maxW="1180px" mx="auto" px={{ base: "20px", md: "32px" }} h="72px" align="center" justify="space-between">
          <HStack gap="10px">
            <Flex w="34px" h="34px" rounded="12px" bg="#5b4ce1" color="white" align="center" justify="center" fontWeight="900">S</Flex>
            <Text fontWeight="800" letterSpacing="-.02em">ShockGraph</Text>
          </HStack>
          <Badge rounded="full" px="12px" py="6px" bg="#eceaff" color="#4b3cc4">Research Preview</Badge>
        </Flex>
      </Box>

      <Box as="main" maxW="1180px" mx="auto" px={{ base: "20px", md: "32px" }} py={{ base: "36px", md: "64px" }}>
        <Grid templateColumns={{ base: "1fr", lg: "minmax(0, 1.18fr) minmax(340px, .82fr)" }} gap={{ base: "28px", lg: "44px" }} alignItems="start">
          <VStack align="stretch" gap="24px">
            <Box>
              <Badge mb="16px" rounded="full" px="12px" py="6px" bg="#fff0ef" color="#c23e38">CPI EVENT LAB</Badge>
              <Heading as="h1" fontSize={{ base: "38px", md: "58px" }} lineHeight="1.06" letterSpacing="-.055em" maxW="760px">
                경제 발표가 내 자산에 남긴 흔적을 읽어보세요.
              </Heading>
              <Text mt="18px" fontSize={{ base: "16px", md: "18px" }} lineHeight="1.75" color="#687086" maxW="680px">
                예측시장의 CPI 발생확률과 ETF 반응을 구분해 보여줍니다. 검증되지 않은 수치는 만들지 않고, 표본과 기준시각을 함께 공개합니다.
              </Text>
            </Box>

            <Box bg="rgba(255,255,255,.9)" border="1px solid" borderColor="#e4e7f0" rounded="24px" p={{ base: "20px", md: "28px" }} boxShadow="0 18px 60px rgba(31,36,66,.07)">
              <Flex justify="space-between" align={{ base: "start", sm: "center" }} direction={{ base: "column", sm: "row" }} gap="12px">
                <Box>
                  <Text fontSize="13px" fontWeight="800" color="#5b4ce1" letterSpacing=".09em">검증된 연구 결과</Text>
                  <Heading as="h2" mt="6px" fontSize={{ base: "24px", md: "30px" }} letterSpacing="-.035em">CPI 0.3% 초과 확률</Heading>
                </Box>
                {researchState === "ready" && <Badge bg="#e9f8ef" color="#197642" rounded="full" px="12px" py="7px">검증 완료</Badge>}
              </Flex>

              {researchState === "loading" && <Flex py="42px" justify="center"><Spinner color="#5b4ce1" /></Flex>}
              {researchState === "error" && (
                <Box mt="24px" rounded="18px" bg="#f4f5f9" p="20px">
                  <Text fontWeight="750">연구 스냅샷을 불러오지 못했습니다.</Text>
                  <Text mt="6px" color="#687086" fontSize="14px">API 실행 상태와 기준 데이터 경로를 확인해 주세요.</Text>
                </Box>
              )}
              {research && researchState === "ready" && (
                <>
                  <SimpleGrid columns={{ base: 1, sm: 3 }} gap="12px" mt="26px">
                    <Metric label="품질 통과 사건" value={`${research.metrics.eligible_events}건`} />
                    <Metric label="동일 기준 비교" value={`${research.independent_event_count}건`} />
                    <Metric label="손실 차이" value={research.metrics.mean_brier_difference.toFixed(4)} accent />
                  </SimpleGrid>
                  <Box mt="18px" rounded="18px" bg="#f2f0ff" p="18px">
                    <Text fontWeight="800" color="#4033aa">예측시장 확률이 단순 과거 비율보다 낮은 오차를 보였습니다.</Text>
                    <Text mt="6px" fontSize="14px" lineHeight="1.65" color="#625d86">이 결과는 CPI 계약 결과에 대한 예비 검증이며 ETF 상승확률이나 투자수익을 뜻하지 않습니다.</Text>
                  </Box>
                  <Box as="details" mt="18px" color="#4d546a">
                    <Box as="summary" fontWeight="750" fontSize="14px">근거와 수치 보기</Box>
                    <SimpleGrid columns={{ base: 1, sm: 2 }} gap="10px" mt="12px" fontSize="14px">
                      <Evidence label="시장확률 Brier" value={research.metrics.raw_market_brier.toFixed(4)} />
                      <Evidence label="과거비율 Brier" value={research.metrics.expanding_historical_brier.toFixed(4)} />
                      <Evidence label="Bootstrap 95% 하한" value={research.metrics.paired_event_bootstrap95[0].toFixed(4)} />
                      <Evidence label="Bootstrap 95% 상한" value={research.metrics.paired_event_bootstrap95[1].toFixed(4)} />
                    </SimpleGrid>
                    <Text mt="12px" fontSize="12px" color="#7b8296">기준시각 {new Date(research.as_of).toLocaleString("ko-KR")}</Text>
                  </Box>
                </>
              )}
            </Box>
          </VStack>

          <Box position={{ lg: "sticky" }} top={{ lg: "96px" }} bg="#171a2b" color="white" rounded="28px" p={{ base: "20px", md: "26px" }} boxShadow="0 24px 70px rgba(23,26,43,.22)">
            <Text fontSize="13px" fontWeight="800" color="#b9b2ff" letterSpacing=".09em">ASSET IMPACT</Text>
            <Heading as="h2" mt="7px" fontSize="27px" letterSpacing="-.035em">자산 반응 살펴보기</Heading>
            <Text mt="8px" color="#afb4c8" fontSize="14px" lineHeight="1.65">관심 자산과 발표 후 구간을 선택하세요.</Text>

            <Text mt="26px" mb="10px" fontSize="13px" color="#afb4c8" fontWeight="700">자산</Text>
            <SimpleGrid columns={2} gap="8px">
              {assets.map((item) => (
                <Button key={item.id} onClick={() => setAsset(item.id)} minH="52px" rounded="15px" bg={asset === item.id ? "#6757eb" : "#25293c"} color="white" border="1px solid" borderColor={asset === item.id ? "#8578ff" : "#353a50"} _hover={{ bg: asset === item.id ? "#7162ef" : "#30354b" }} aria-pressed={asset === item.id}>
                  {item.id}
                </Button>
              ))}
            </SimpleGrid>

            <Text mt="20px" mb="10px" fontSize="13px" color="#afb4c8" fontWeight="700">발표 후 구간</Text>
            <HStack bg="#25293c" p="5px" rounded="15px" gap="4px">
              {(["m5", "m30"] as Horizon[]).map((item) => (
                <Button key={item} flex="1" onClick={() => setHorizon(item)} rounded="11px" bg={horizon === item ? "white" : "transparent"} color={horizon === item ? "#171a2b" : "#c3c7d5"} _hover={{ bg: horizon === item ? "white" : "#30354b" }} aria-pressed={horizon === item}>
                  {item === "m5" ? "5분" : "30분"}
                </Button>
              ))}
            </HStack>

            <Box mt="24px" p="20px" rounded="20px" bg="linear-gradient(145deg, rgba(103,87,235,.24), rgba(255,255,255,.06))" border="1px solid" borderColor="#454963">
              <Flex justify="space-between" align="center">
                <Box>
                  <Text fontWeight="850" fontSize="20px">{asset} · {selectedAsset.name}</Text>
                  <Text color="#afb4c8" fontSize="13px" mt="3px">{selectedAsset.role} · 발표 후 {horizon === "m5" ? "5분" : "30분"}</Text>
                </Box>
                {analysisState === "loading" && <Spinner size="sm" color="#b9b2ff" />}
              </Flex>

              {analysisState === "error" && <StatusMessage title="API 연결을 확인해 주세요" body="분석 상태를 불러오지 못했습니다." />}
              {analysisState === "ready" && analysis?.status === "insufficient_data" && analysis.diagnostic_test_events === undefined && (
                <StatusMessage title="평가 보고서 연결 대기 중" body="검증된 평가 보고서가 연결되면 실제 표본 수와 비교 결과를 표시합니다." />
              )}
              {analysisState === "ready" && analysis?.diagnostic_test_events !== undefined && (
                <Box mt="18px">
                  <Badge colorPalette="orange">탐색적 과거 평가</Badge>
                  <Text mt="12px" fontWeight="700">공통 사건 {analysis.independent_event_count}건</Text>
                  <Text mt="6px" fontSize="13px" color="#c3c7d5">
                    초기 5건 기준 · 시험 {analysis.diagnostic_test_events}건
                  </Text>
                  {analysis.comparison ? (
                    <VStack align="stretch" gap="7px" mt="14px" fontSize="13px">
                      <Text>과거 발생비율 CRPS: {analysis.comparison.historical_crps.toFixed(6)}</Text>
                      <Text>Kalshi 확률 CRPS: {analysis.comparison.kalshi_crps.toFixed(6)}</Text>
                      <Text>차이: {analysis.comparison.mean_crps_difference.toFixed(6)} (음수면 Kalshi 오차가 작음)</Text>
                      <Text>탐색적 Bootstrap 95% 구간: [{analysis.comparison.paired_event_bootstrap95.map((v) => v.toFixed(6)).join(", ")}]</Text>
                    </VStack>
                  ) : <Text mt="12px" fontSize="13px">시험 표본이 부족해 비교 수치를 표시하지 않습니다.</Text>}
                  <Text mt="14px" fontSize="13px" color="#f3cf95">
                    초기 20건 연구 기준: 시험 {analysis.research_test_events}/{analysis.research_required_test_events}건
                    {analysis.research_status === "insufficient_test_events" ? " · 주요 평가 보류" : " · 탐색 평가 가능"}
                  </Text>
                  <Text mt="10px" fontSize="12px" color="#afb4c8" lineHeight="1.7">
                    같은 사건에서 과거 발생비율과 Kalshi 확률을 비교했습니다. 전통 거시정보 대비 검증과 미래 수익률 예측은 아직 제공하지 않습니다.
                  </Text>
                </Box>
              )}
            </Box>

            <Flex mt="18px" gap="10px" align="start">
              <Box mt="3px" w="8px" h="8px" rounded="full" bg="#f3b74f" flexShrink="0" />
              <Text fontSize="12px" lineHeight="1.6" color="#afb4c8">주 분석은 SPY·TLT입니다. 보고서가 없으면 수치를 표시하지 않으며, 곡률·DNN 방법론은 배포 이후 추가 검증합니다.</Text>
            </Flex>
          </Box>
        </Grid>
      </Box>
    </Box>
  );
}

function Metric({ label, value, accent = false }: { label: string; value: string; accent?: boolean }) {
  return (
    <Box rounded="17px" border="1px solid" borderColor="#e4e7f0" bg={accent ? "#fff6f5" : "#fafbfe"} p="16px">
      <Text fontSize="12px" color="#747b90">{label}</Text>
      <Text mt="5px" fontSize="24px" fontWeight="850" letterSpacing="-.03em" color={accent ? "#c6403a" : "#171a2b"}>{value}</Text>
    </Box>
  );
}

function Evidence({ label, value }: { label: string; value: string }) {
  return <Flex justify="space-between" rounded="12px" bg="#f7f8fb" p="11px"><Text>{label}</Text><Text fontWeight="800">{value}</Text></Flex>;
}

function StatusMessage({ title, body }: { title: string; body: string }) {
  return (
    <Box mt="20px">
      <Text fontSize="26px" fontWeight="850" letterSpacing="-.04em">—</Text>
      <Text mt="8px" fontWeight="800">{title}</Text>
      <Text mt="5px" color="#afb4c8" fontSize="13px" lineHeight="1.6">{body}</Text>
    </Box>
  );
}
