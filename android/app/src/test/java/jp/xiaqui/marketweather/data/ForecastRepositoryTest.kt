package jp.xiaqui.marketweather.data
import org.junit.Assert.*
import org.junit.Test
class ForecastRepositoryTest {
    private val forecast by lazy {
        val stream = requireNotNull(javaClass.classLoader?.getResourceAsStream("forecast.json"))
        stream.bufferedReader().use { ForecastRepository().parse(it) }
    }
    @Test fun `forecast JSON parses and contains four markets`() {
        assertEquals(4, forecast.markets.size)
        assertTrue(forecast.generatedAt.isNotBlank())
    }
    @Test fun `all forecast values obey their constraints`() {
        forecast.markets.forEach {
            assertTrue("${it.id} up_probability", it.upProbability in 0.0..1.0)
            assertTrue("${it.id} confidence", it.confidence in 0.0..1.0)
            assertTrue("${it.id} range", it.rangeLow < it.rangeHigh)
        }
    }
}
