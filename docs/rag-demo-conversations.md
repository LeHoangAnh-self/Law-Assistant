# Demo Hội Thoại RAG

Trang này trình bày log hội thoại xuất từ UI test của Law Assistant theo dạng case study dễ đọc để dùng trong README, demo hoặc review kỹ thuật. Nội dung chỉ là ví dụ nghiên cứu pháp luật, không thay thế tư vấn pháp lý chính thức.

## Tình Huống Demo

- **Chủ đề:** miễn thuế thu nhập cá nhân khi bán căn hộ được cho là nhà ở duy nhất.
- **Ngôn ngữ:** tiếng Việt.
- **Yêu cầu:** trả lời theo hướng luật sư, gồm kết luận, phân tích rủi ro, giấy tờ cần kiểm tra và khuyến nghị thực tế.
- **Điểm thể hiện:** RAG trả lời có cấu trúc, phân tích theo từng người đồng sở hữu, và kèm nguồn văn bản pháp luật được truy xuất.

<details open>
<summary>Câu hỏi người dùng</summary>

Hôm nay là 30/06/2026.

Tôi và vợ đang đứng tên chung trên sổ hồng một căn hộ tại TP.HCM, mua từ năm 2020. Đây là nơi ở chính của gia đình và chúng tôi muốn bán toàn bộ căn hộ này cho người mua bên ngoài.

Tôi không đứng tên bất kỳ nhà đất nào khác. Tuy nhiên, vợ tôi đang đứng tên 1/3 quyền sử dụng đất ở trong một thửa đất do cha mẹ vợ để lại ở Long An.

Chúng tôi muốn hỏi:

Việc bán căn hộ này có được miễn thuế thu nhập cá nhân vì là “nhà ở duy nhất” không?
Nếu chỉ một trong hai vợ chồng đủ điều kiện miễn thuế thì xử lý thế nào?
Có nên chuyển phần đất ở Long An cho người thân trước khi bán căn hộ để được miễn thuế không?
Cần chuẩn bị giấy tờ gì để giảm rủi ro khi làm hồ sơ thuế?

Hãy tư vấn theo hướng luật sư: kết luận, phân tích rủi ro, giấy tờ cần kiểm tra, và khuyến nghị thực tế. Không chỉ trả lời “có/không”.

</details>

## Hội Thoại Đề Xuất Cho Demo

Đây là lần chạy nên dùng khi trình bày repo vì classification cụ thể hơn và các nguồn truy xuất tập trung hơn vào cùng nhóm văn bản thuế thu nhập cá nhân.

| Thuộc tính | Giá trị |
| --- | --- |
| Thời điểm export | `2026-06-30 12:57:11.999 UTC` |
| Conversation ID | `7cf1e188-3117-41fb-a818-a547c76240ae` |
| UI | `UI_test` |
| RAG API | `rag-service` / `ok` |
| Top K | `6` |
| Classification | `tax.pit_real_estate_exemption` |
| Số nguồn truy xuất | `6` |

### Câu Trả Lời

#### 1. Kết luận

- **Anh có cơ sở được miễn thuế TNCN đối với phần chuyển nhượng của anh** nếu đúng là anh không đứng tên bất kỳ nhà ở/quyền sử dụng đất ở nào khác, căn hộ đã đứng tên từ năm 2020 và bán **toàn bộ** căn hộ [6], [1].  
- **Vợ anh không đủ điều kiện miễn thuế đối với phần của vợ** vì vợ đang có thêm **1/3 quyền sử dụng đất ở tại Long An**, tức có quyền sử dụng đất ở khác ngoài căn hộ chung [6].  
- Nếu chỉ anh được miễn, **nghĩa vụ thuế phải tách riêng theo từng người đồng sở hữu**; nếu không có tài liệu hợp pháp xác định tỷ lệ sở hữu thì chia bình quân, thường là mỗi người 1/2 theo trích đoạn được cung cấp [2].  
- Không nên chỉ “chuyển trước” phần đất Long An để tạo điều kiện miễn thuế nếu giao dịch không thực chất; trích đoạn chỉ cho biết việc miễn do cá nhân tự khai và nếu khai sai sẽ bị truy thu, phạt, còn chưa có đủ trích đoạn về xử lý giao dịch chuyển nhượng/tặng cho trước thời điểm bán [1].

#### 2. Luật áp dụng tại ngày nêu trong câu hỏi

Các trích đoạn đang có là từ **Thông tư 111/2013/TT-BTC**, được ghi nhận “hết hiệu lực một phần”, nhưng trích đoạn không thể hiện chính các nội dung về miễn thuế nhà ở duy nhất và phân bổ thuế đồng sở hữu đã bị hết hiệu lực; vì vậy tôi chỉ dùng thận trọng đúng các nội dung được trích.

Điều kiện miễn thuế đối với nhà ở/đất ở duy nhất gồm: cá nhân chỉ có duy nhất một nhà ở hoặc quyền sử dụng một thửa đất ở tại thời điểm chuyển nhượng; việc xác định căn cứ vào Giấy chứng nhận; nếu tài sản chung thì chỉ người chưa có nhà/đất ở khác được miễn [6]. Ngoài ra, người chuyển nhượng phải có quyền sở hữu/quyền sử dụng tối thiểu 183 ngày và phải chuyển nhượng toàn bộ nhà ở/đất ở; việc miễn thuế là do cá nhân tự khai và tự chịu trách nhiệm [1].

#### 3. Áp dụng vào từng người/từng sự kiện

**Đối với anh:** anh không đứng tên nhà đất nào khác, căn hộ mua từ năm 2020 nên đã quá 183 ngày, và dự kiến bán toàn bộ căn hộ; các dữ kiện này khớp điều kiện “nhà ở, đất ở duy nhất” trong trích đoạn [6], [1]. Vì vậy, **anh đủ điều kiện miễn thuế đối với phần sở hữu của anh**, với điều kiện hồ sơ thực tế không phát sinh nhà/đất ở khác đứng tên anh [6].

**Đối với vợ anh:** vợ đang đứng tên 1/3 quyền sử dụng đất ở tại Long An, nên không còn là người “chưa có quyền sở hữu nhà ở, quyền sử dụng đất ở nơi khác”; trường hợp vợ chồng có nhà chung nhưng một bên còn có nhà/đất ở riêng thì bên có nhà/đất ở riêng không được miễn [6]. Vì vậy, **vợ anh không đủ điều kiện miễn thuế đối với phần sở hữu của vợ** [6].

**Về cách tính/tách nghĩa vụ:** khi chuyển nhượng bất động sản đồng sở hữu, nghĩa vụ thuế được xác định riêng theo tỷ lệ sở hữu; nếu không có tài liệu hợp pháp về tỷ lệ thì xác định theo tỷ lệ bình quân [2]. Do đó, nếu sổ hồng/hồ sơ không ghi tỷ lệ khác, phần không được miễn của vợ có thể bị xác định bình quân là **1/2 giá trị chuyển nhượng** để tính thuế theo quy định áp dụng cho phần của vợ [2].

#### 4. Phân tích rủi ro

Rủi ro lớn nhất là **hồ sơ của vợ**: chỉ cần vợ còn đứng tên quyền sử dụng đất ở tại Long An tại thời điểm chuyển nhượng căn hộ thì phần của vợ không được miễn theo trích đoạn [6].  

Rủi ro thứ hai là **tự khai sai**: Thông tư nêu rõ nhà ở/đất ở duy nhất được miễn do cá nhân tự khai và chịu trách nhiệm; nếu phát hiện không đúng sẽ bị truy thu thuế và phạt vi phạm pháp luật thuế [1].  

Về việc chuyển phần đất Long An cho người thân trước khi bán căn hộ: trích đoạn chỉ cho thấy điều kiện được xét tại “thời điểm chuyển nhượng” căn hộ [6], nhưng chưa có trích đoạn về thuế/phí của giao dịch chuyển phần đất, thời điểm hoàn tất sang tên, hoặc quy định chống lạm dụng. Vì vậy, **chưa đủ căn cứ để khẳng định phương án này an toàn hoặc chắc chắn giúp miễn thuế**.

#### 5. Giấy tờ cần kiểm tra

- Sổ hồng căn hộ TP.HCM: ngày cấp, tên chủ sở hữu, có ghi tỷ lệ sở hữu hay không, và căn hộ có được chuyển nhượng toàn bộ không [1], [2].  
- Giấy tờ về phần đất Long An của vợ: có phải là **đất ở** không, vợ còn đứng tên tại thời điểm bán căn hộ không [6].  
- Tài liệu hợp pháp về tỷ lệ sở hữu căn hộ: thỏa thuận góp vốn, tài liệu phân chia, hoặc giấy tờ khác; nếu không có, nghĩa vụ thuế từng người có thể bị chia bình quân [2].  
- Bản tự khai/cam kết về nhà ở, đất ở duy nhất của anh; cần khai trung thực vì khai sai có thể bị truy thu và phạt [1].

#### 6. Khuyến nghị thực tế

Anh nên làm hồ sơ theo hướng: **anh xin miễn thuế cho phần của anh; vợ kê khai nộp thuế cho phần của vợ**. Không nên nộp hồ sơ theo hướng cả hai vợ chồng đều được miễn nếu vợ vẫn đứng tên đất ở Long An, vì trích đoạn quy định bên có nhà/đất ở riêng không được miễn [6].  

Nếu cân nhắc chuyển phần đất Long An trước, chỉ nên thực hiện khi đó là giao dịch thật, hoàn tất sang tên trước thời điểm bán căn hộ, và đã kiểm tra riêng nghĩa vụ thuế/phí của giao dịch đó; các trích đoạn hiện tại chưa đủ để tư vấn chắc chắn về phương án này.

#### 7. Điều gì có thể làm thay đổi câu trả lời

Câu trả lời sẽ thay đổi nếu: phần đất Long An không phải là **đất ở**; vợ không còn đứng tên tại thời điểm chuyển nhượng căn hộ; sổ hồng/hồ sơ căn hộ ghi tỷ lệ sở hữu khác 1/2; hoặc có văn bản hiện hành khác về hồ sơ, thủ tục, chống tránh thuế mà hiện chưa được cung cấp trong trích đoạn.

### Nguồn Được Truy Xuất

| # | Văn bản | Số hiệu | Loại | Hiệu lực | Điểm | Chunk |
| ---: | --- | --- | --- | --- | ---: | --- |
| 1 | Thông tư số 111/2013/TT-BTC Hướng dẫn thực hiện Luật Thuế thu nhập cá nhân, Luật sửa đổi, bổ sung một số điều của Luật thuế thu nhập cá nhân và Nghị định số 65/2013/NĐ-CP của Chính phủ quy định chi tiết một số điều của Luật Thuế thu nhập cá nhân và Luật sửa đổi, bổ sung một số điều của Luật thuế thu nhập cá nhân | 111/2013/TT-BTC | Thông tư | Hết hiệu lực một phần | 20.819 | `37590:28` |
| 2 | Thông tư số 111/2013/TT-BTC Hướng dẫn thực hiện Luật Thuế thu nhập cá nhân, Luật sửa đổi, bổ sung một số điều của Luật thuế thu nhập cá nhân và Nghị định số 65/2013/NĐ-CP của Chính phủ quy định chi tiết một số điều của Luật Thuế thu nhập cá nhân và Luật sửa đổi, bổ sung một số điều của Luật thuế thu nhập cá nhân | 111/2013/TT-BTC | Thông tư | Hết hiệu lực một phần | 12.000 | `37590:101` |
| 3 | Thông tư số 111/2013/TT-BTC Hướng dẫn thực hiện Luật Thuế thu nhập cá nhân, Luật sửa đổi, bổ sung một số điều của Luật thuế thu nhập cá nhân và Nghị định số 65/2013/NĐ-CP của Chính phủ quy định chi tiết một số điều của Luật Thuế thu nhập cá nhân và Luật sửa đổi, bổ sung một số điều của Luật thuế thu nhập cá nhân | 111/2013/TT-BTC | Thông tư | Hết hiệu lực một phần | 9.000 | `37590:100` |
| 4 | Thông tư số 111/2013/TT-BTC Hướng dẫn thực hiện Luật Thuế thu nhập cá nhân, Luật sửa đổi, bổ sung một số điều của Luật thuế thu nhập cá nhân và Nghị định số 65/2013/NĐ-CP của Chính phủ quy định chi tiết một số điều của Luật Thuế thu nhập cá nhân và Luật sửa đổi, bổ sung một số điều của Luật thuế thu nhập cá nhân | 111/2013/TT-BTC | Thông tư | Hết hiệu lực một phần | 3.000 | `37590:102` |
| 5 | Thông tư số 111/2013/TT-BTC Hướng dẫn thực hiện Luật Thuế thu nhập cá nhân, Luật sửa đổi, bổ sung một số điều của Luật thuế thu nhập cá nhân và Nghị định số 65/2013/NĐ-CP của Chính phủ quy định chi tiết một số điều của Luật Thuế thu nhập cá nhân và Luật sửa đổi, bổ sung một số điều của Luật thuế thu nhập cá nhân | 111/2013/TT-BTC | Thông tư | Hết hiệu lực một phần | 3.000 | `37590:5` |
| 6 | Thông tư số 111/2013/TT-BTC Hướng dẫn thực hiện Luật Thuế thu nhập cá nhân, Luật sửa đổi, bổ sung một số điều của Luật thuế thu nhập cá nhân và Nghị định số 65/2013/NĐ-CP của Chính phủ quy định chi tiết một số điều của Luật Thuế thu nhập cá nhân và Luật sửa đổi, bổ sung một số điều của Luật thuế thu nhập cá nhân | 111/2013/TT-BTC | Thông tư | Hết hiệu lực một phần | 15.794 | `37590:27` |

<details>
<summary>Xem truy vấn retrieval</summary>

```text
Hôm nay là 30/06/2026. Tôi và vợ đang đứng tên chung trên sổ hồng một căn hộ tại TP.HCM, mua từ năm 2020. Đây là nơi ở chính của gia đình và chúng tôi muốn bán toàn bộ căn hộ này cho người mua bên ngoài. Tôi không đứng tên bất kỳ nhà đất nào khác. Tuy nhiên, vợ tôi đang đứng tên 1/3 quyền sử dụng đất ở trong một thửa đất do cha mẹ vợ để lại ở Long An. Chúng tôi muốn hỏi: Việc bán căn hộ này có được miễn thuế thu nhập cá nhân vì là “nhà ở duy nhất” không? Nếu chỉ một trong hai vợ chồng đủ điều kiện miễn thuế thì xử lý thế nào? Có nên chuyển phần đất ở Long An cho người thân trước khi bán căn hộ để được miễn thuế không? Cần chuẩn bị giấy tờ gì để giảm rủi ro khi làm hồ sơ thuế? Hãy tư vấn theo hướng luật sư: kết luận, phân tích rủi ro, giấy tờ cần kiểm tra, và khuyến nghị thực tế. Không chỉ trả lời “có/không”.
---
Luật Thuế thu nhập cá nhân hiện hành miễn thuế thu nhập cá nhân chuyển nhượng bất động sản
---
miễn thuế TNCN chuyển nhượng nhà ở duy nhất quyền sử dụng đất ở duy nhất
---
Thông tư 111/2013/TT-BTC Điều 3 nhà ở duy nhất đất ở duy nhất miễn thuế
---
Luật Thuế thu nhập cá nhân Điều 4 miễn thuế chuyển nhượng nhà ở đất ở duy nhất
---
hồ sơ miễn thuế TNCN chuyển nhượng nhà ở duy nhất cam kết nhà đất duy nhất
---
chuyển nhượng nhà đất đồng sở hữu vợ chồng miễn thuế TNCN
---
mỗi cá nhân đồng sở hữu bất động sản xác định nghĩa vụ thuế theo phần sở hữu
---
vợ chồng đồng sở hữu một người có nhà đất riêng miễn thuế nhà ở duy nhất
---
Thông tư 111/2013/TT-BTC Điều 12 đồng sở hữu nghĩa vụ thuế tỷ lệ bình quân
---
chuyển nhượng bất động sản cá nhân cư trú thuế TNCN miễn thuế nhà ở duy nhất
```
</details>

## Log So Sánh

<details>
<summary>Xem lần chạy baseline trước đó</summary>

| Thuộc tính | Giá trị |
| --- | --- |
| Thời điểm export | `2026-06-30 10:10:38.612 UTC` |
| Conversation ID | `01ea952f-00df-4ee7-a800-ba263a00dfb9` |
| UI | `UI_test` |
| RAG API | `rag-service` / `ok` |
| Top K | `6` |
| Classification | `tax` |
| Số nguồn truy xuất | `6` |

### Câu Trả Lời Baseline

#### 1. Kết luận

- **Chồng:** theo dữ kiện anh không đứng tên nhà/đất nào khác, căn hộ mua từ 2020 và bán **toàn bộ**, nên **đủ điều kiện miễn thuế TNCN đối với phần thu nhập thuộc phần sở hữu của anh**, nếu Giấy chứng nhận và hồ sơ thực tế xác nhận đúng các điều kiện này [1], [5].  
- **Vợ:** hiện đang đứng tên **1/3 quyền sử dụng đất ở tại Long An**, nên tại thời điểm bán căn hộ, vợ **không đủ điều kiện “chỉ có một nhà ở hoặc một thửa đất ở”**; phần thu nhập của vợ từ bán căn hộ **không được miễn** nếu vẫn còn đứng tên phần đất đó [1], [5].  
- Vì vậy, **không nên hiểu toàn bộ căn hộ được miễn thuế** chỉ vì đây là nơi ở chính của gia đình; quy định trong trích đoạn xét theo **từng cá nhân** và tình trạng nhà/đất của từng người [1], [5].

#### 2. Luật áp dụng tại ngày nêu trong câu hỏi

Các trích đoạn trực tiếp áp dụng là Nghị định 65/2013/NĐ-CP và Thông tư 111/2013/TT-BTC; cả hai được cung cấp với tình trạng “hết hiệu lực một phần”, nên cần kiểm tra thêm văn bản hiện hành tại thời điểm nộp hồ sơ, nhưng các trích đoạn đang nêu rõ điều kiện miễn thuế “nhà ở, đất ở duy nhất” [1], [5].  

Điều kiện chính gồm: tại thời điểm chuyển nhượng cá nhân chỉ có quyền sở hữu/quyền sử dụng **một nhà ở hoặc một thửa đất ở**, đã có quyền tối thiểu **183 ngày**, và chuyển nhượng **toàn bộ** nhà ở/đất ở đó [5]. Thông tư cũng nêu việc miễn thuế do cá nhân tự khai, nếu khai sai thì bị truy thu và phạt [1].

#### 3. Áp dụng vào từng người/từng sự kiện

**Đối với chồng:** anh không có nhà/đất nào khác, căn hộ mua từ 2020 nên về thời gian đã vượt 183 ngày nếu ngày cấp Giấy chứng nhận cũng từ 2020 hoặc trước thời điểm bán trên 183 ngày; việc bán toàn bộ căn hộ cũng phù hợp điều kiện “chuyển nhượng toàn bộ nhà ở, đất ở” [1], [5].  

**Đối với vợ:** phần 1/3 đất ở Long An vẫn là quyền sử dụng đất ở khác. Quy định yêu cầu cá nhân tại thời điểm chuyển nhượng “chỉ có quyền sở hữu, quyền sử dụng một nhà ở hoặc một thửa đất ở”, nên vợ không đạt điều kiện nếu vẫn đứng tên quyền sử dụng đất ở Long An khi bán căn hộ [5].  

**Nếu chỉ một người đủ điều kiện:** nên tách nghĩa vụ thuế theo phần sở hữu của từng người. Với dữ kiện sổ hồng đứng tên chung vợ chồng nhưng chưa nêu tỷ lệ, cần kiểm tra Giấy chứng nhận/hợp đồng; các trích đoạn không nêu quy tắc chia mặc định, nên hồ sơ thuế cần thể hiện rõ phần thu nhập của chồng được đề nghị miễn và phần của vợ không được miễn nếu vợ vẫn có đất ở Long An [1], [5].

#### 4. Phân tích rủi ro

Rủi ro lớn nhất là **kê khai “nhà ở duy nhất” cho cả hai vợ chồng** trong khi vợ đang có 1/3 đất ở Long An; trích đoạn nêu rõ cá nhân tự khai và nếu phát hiện không đúng thì bị **truy thu thuế và phạt** [1].  

Việc căn hộ là “nơi ở chính” không được nêu trong các trích đoạn như một điều kiện thay thế cho tiêu chí “chỉ có một nhà ở hoặc một thửa đất ở”, nên không đủ để giúp vợ được miễn khi còn đất ở khác [5].  

Nếu chuyển phần đất Long An cho người thân trước khi bán căn hộ, cần bảo đảm việc chuyển là thật, hoàn tất trước thời điểm bán và thể hiện trên Giấy chứng nhận/hồ sơ đăng ký, vì việc xác định quyền sở hữu, quyền sử dụng căn cứ vào Giấy chứng nhận [5]. Nếu chỉ chuyển hình thức nhưng kê khai không đúng tình trạng thực tế thì vẫn có rủi ro bị xử lý theo cơ chế truy thu/phạt khi kê khai sai [1].

#### 5. Giấy tờ cần kiểm tra

- Sổ hồng căn hộ: ngày cấp, tên chủ sở hữu, tỷ lệ sở hữu nếu có, và bảo đảm giao dịch là bán **toàn bộ** căn hộ [1], [5].  
- Giấy tờ đất Long An: xác nhận đúng là **đất ở**, vợ đứng tên 1/3, thời điểm đứng tên và tình trạng hiện tại tại ngày ký hợp đồng bán căn hộ [5].  
- Hồ sơ chứng minh chồng không có nhà ở/đất ở khác; vì trích đoạn quy định cá nhân tự khai và tự chịu trách nhiệm, nên nên chuẩn bị bản cam kết/kê khai riêng cho chồng [1].  
- Nếu vợ chuyển phần đất Long An trước khi bán: hợp đồng tặng cho/chuyển nhượng, hồ sơ đăng ký biến động, Giấy chứng nhận sau khi cập nhật không còn tên vợ.  
- Nếu tặng cho người thân: cần kiểm tra người nhận có thuộc nhóm quan hệ được miễn TNCN đối với quà tặng bất động sản hay không, như cha mẹ với con, vợ chồng, anh chị em ruột... [5].

#### 6. Khuyến nghị thực tế

Không nên nộp hồ sơ miễn thuế cho cả hai vợ chồng nếu vợ vẫn đứng tên 1/3 đất ở Long An. Phương án an toàn hơn là: **chồng kê khai miễn cho phần của chồng**, còn **vợ kê khai nộp thuế cho phần của vợ**, trừ khi trước thời điểm bán vợ đã không còn quyền sử dụng đất ở Long An và hồ sơ đăng ký thể hiện rõ việc này [1], [5].  

Nếu muốn chuyển phần đất Long An, chỉ nên làm khi có nhu cầu tài sản thật sự, hoàn tất đăng ký trước khi ký hợp đồng bán căn hộ, và kiểm tra nghĩa vụ thuế/phí của giao dịch đó; trích đoạn chỉ cho thấy một số trường hợp quà tặng/thừa kế bất động sản giữa người thân được miễn TNCN, chưa đủ để kết luận toàn bộ chi phí khác [5].  

#### 7. Điều gì có thể làm thay đổi câu trả lời

Câu trả lời có thể thay đổi nếu: đất Long An không phải là **đất ở**; vợ đã hoàn tất xóa tên khỏi Giấy chứng nhận trước thời điểm bán căn hộ; sổ hồng căn hộ ghi tỷ lệ sở hữu khác 50/50; hoặc có văn bản hiện hành đến ngày 30/06/2026 sửa đổi trực tiếp điều kiện miễn thuế mà các trích đoạn chưa cung cấp.

### Nguồn Được Truy Xuất Trong Baseline

| # | Văn bản | Số hiệu | Loại | Hiệu lực | Điểm | Chunk |
| ---: | --- | --- | --- | --- | ---: | --- |
| 1 | Thông tư số 111/2013/TT-BTC Hướng dẫn thực hiện Luật Thuế thu nhập cá nhân, Luật sửa đổi, bổ sung một số điều của Luật thuế thu nhập cá nhân và Nghị định số 65/2013/NĐ-CP của Chính phủ quy định chi tiết một số điều của Luật Thuế thu nhập cá nhân và Luật sửa đổi, bổ sung một số điều của Luật thuế thu nhập cá nhân | 111/2013/TT-BTC | Thông tư | Hết hiệu lực một phần | 12.628 | `37590:28` |
| 2 | Thông tư số 111/2013/TT-BTC Hướng dẫn thực hiện Luật Thuế thu nhập cá nhân, Luật sửa đổi, bổ sung một số điều của Luật thuế thu nhập cá nhân và Nghị định số 65/2013/NĐ-CP của Chính phủ quy định chi tiết một số điều của Luật Thuế thu nhập cá nhân và Luật sửa đổi, bổ sung một số điều của Luật thuế thu nhập cá nhân | 111/2013/TT-BTC | Thông tư | Hết hiệu lực một phần | 8.269 | `37590:7` |
| 3 | Nghị định số 14/2018/NĐ-CP quy định chi tiết về hoạt động thương mại biên giới | 14/2018/NĐ-CP | Nghị định | Còn hiệu lực | 2.016 | `128277:6` |
| 4 | Nghị định số 65/2013/NĐ-CP Quy định chi tiết một số điều của Luật Thuế thu nhập cá nhân và Luật Sửa đổi, bổ sung một số điều của Luật Thuế thu nhập cá nhân | 65/2013/NĐ-CP | Nghị định | Hết hiệu lực một phần | 1.333 | `30638:32` |
| 5 | Nghị định số 65/2013/NĐ-CP Quy định chi tiết một số điều của Luật Thuế thu nhập cá nhân và Luật Sửa đổi, bổ sung một số điều của Luật Thuế thu nhập cá nhân | 65/2013/NĐ-CP | Nghị định | Hết hiệu lực một phần | 0.529 | `30638:9` |
| 6 | Nghị định số 05/2009/NĐ- CP VĂN BẢN TRÙNG Quy định chi tiết thi hành Pháp lệnh thuế tài nguyên và Pháp lệnh sửa đổi, bổ sung Điều 6 Pháp lệnh thuế tài nguyên | 05/2009/NĐ- CP VĂN BẢN TRÙNG | Nghị định | Còn hiệu lực | -3.271 | `12660:8` |

<details>
<summary>Xem truy vấn retrieval</summary>

```text
Hôm nay là 30/06/2026. Tôi và vợ đang đứng tên chung trên sổ hồng một căn hộ tại TP.HCM, mua từ năm 2020. Đây là nơi ở chính của gia đình và chúng tôi muốn bán toàn bộ căn hộ này cho người mua bên ngoài. Tôi không đứng tên bất kỳ nhà đất nào khác. Tuy nhiên, vợ tôi đang đứng tên 1/3 quyền sử dụng đất ở trong một thửa đất do cha mẹ vợ để lại ở Long An. Chúng tôi muốn hỏi: Việc bán căn hộ này có được miễn thuế thu nhập cá nhân vì là “nhà ở duy nhất” không? Nếu chỉ một trong hai vợ chồng đủ điều kiện miễn thuế thì xử lý thế nào? Có nên chuyển phần đất ở Long An cho người thân trước khi bán căn hộ để được miễn thuế không? Cần chuẩn bị giấy tờ gì để giảm rủi ro khi làm hồ sơ thuế? Hãy tư vấn theo hướng luật sư: kết luận, phân tích rủi ro, giấy tờ cần kiểm tra, và khuyến nghị thực tế. Không chỉ trả lời “có/không”.
---
Luật Thuế thu nhập cá nhân hiện hành miễn thuế thu nhập cá nhân chuyển nhượng bất động sản
---
miễn thuế TNCN chuyển nhượng nhà ở duy nhất quyền sử dụng đất ở duy nhất
---
Thông tư 111/2013/TT-BTC Điều 3 nhà ở duy nhất đất ở duy nhất miễn thuế
---
Luật Thuế thu nhập cá nhân Điều 4 miễn thuế chuyển nhượng nhà ở đất ở duy nhất
---
hồ sơ miễn thuế TNCN chuyển nhượng nhà ở duy nhất cam kết nhà đất duy nhất
---
chuyển nhượng nhà đất đồng sở hữu vợ chồng miễn thuế TNCN
---
mỗi cá nhân đồng sở hữu bất động sản xác định nghĩa vụ thuế theo phần sở hữu
---
vợ chồng đồng sở hữu một người có nhà đất riêng miễn thuế nhà ở duy nhất
---
Thông tư 111/2013/TT-BTC Điều 12 đồng sở hữu nghĩa vụ thuế tỷ lệ bình quân
---
chuyển nhượng bất động sản cá nhân cư trú thuế TNCN miễn thuế nhà ở duy nhất
```
</details>

</details>

## Ghi Chú Trình Bày

- Trang này không nhúng API key, biến môi trường, hoặc raw JSON export.
- Bảng nguồn chỉ hiển thị metadata chính để người đọc thấy RAG đã truy xuất văn bản nào.
- Lần chạy baseline được giữ để minh họa quá trình so sánh chất lượng retrieval, nhưng phần demo chính nên dùng lần chạy đề xuất ở trên.
