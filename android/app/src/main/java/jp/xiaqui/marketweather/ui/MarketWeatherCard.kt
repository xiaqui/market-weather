package jp.xiaqui.marketweather.ui
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import jp.xiaqui.marketweather.model.Market
import java.text.DecimalFormat
private val weather = mapOf("sunny" to ("☀️" to "晴れ"), "partly_cloudy" to ("🌤️" to "晴れ時々曇り"), "cloudy" to ("☁️" to "曇り"), "rainy" to ("🌧️" to "雨"), "storm" to ("⛈️" to "荒天"))
private val risks = mapOf("calm" to "安定", "normal" to "通常", "caution" to "注意", "storm" to "荒天")
private val number = DecimalFormat("#,##0.##")
@Composable
fun MarketWeatherCard(market: Market, onClick: () -> Unit) {
    val condition = weather[market.weather] ?: ("❔" to market.weather)
    Card(modifier = Modifier.fillMaxWidth().clickable(onClick = onClick), shape = RoundedCornerShape(22.dp), colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface), elevation = CardDefaults.cardElevation(2.dp)) {
        Column(Modifier.padding(20.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) {
                    Text(market.name, fontWeight = FontWeight.Bold, fontSize = 19.sp)
                    Text(number.format(market.current), fontWeight = FontWeight.ExtraBold, fontSize = 28.sp)
                }
                Column(horizontalAlignment = Alignment.CenterHorizontally) {
                    Text(condition.first, fontSize = 42.sp)
                    Text(condition.second, style = MaterialTheme.typography.labelMedium)
                }
            }
            Spacer(Modifier.height(14.dp))
            HorizontalDivider(color = MaterialTheme.colorScheme.outlineVariant)
            Spacer(Modifier.height(12.dp))
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                Stat("上昇確率", "${(market.upProbability * 100).toInt()}%")
                Stat("信頼度", "${(market.confidence * 100).toInt()}%")
                Stat("リスク", risks[market.risk] ?: market.risk)
            }
            Spacer(Modifier.height(10.dp))
            Text("予想レンジ  ${number.format(market.rangeLow)} ～ ${number.format(market.rangeHigh)}", style = MaterialTheme.typography.bodyMedium)
        }
    }
}
@Composable private fun Stat(label: String, value: String) = Column { Text(label, style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant); Text(value, fontWeight = FontWeight.Bold) }
fun weatherLabel(value: String) = weather[value]?.second ?: value
fun riskLabel(value: String) = risks[value] ?: value
fun formattedNumber(value: Double) = number.format(value)
