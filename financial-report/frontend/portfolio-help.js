/* Portfolio help: compact, accessible, no extra modal dependencies. */
(()=>{'use strict';
const root=document.getElementById('portfolio');if(!root)return;
const copy={
 templates:['Mẫu quản trị danh mục','Mẫu quản trị là bộ nguyên tắc phân bổ và theo dõi tỷ trọng trong danh mục. Mẫu không tự tạo giao dịch. Hệ thống đối chiếu vị thế thực tế với tỷ trọng mục tiêu khi có dữ liệu phù hợp.'],
 cash:['Tiền mặt mục tiêu','Tỷ lệ tiền mặt mong muốn duy trì trong danh mục. Mức này được dùng khi tính tỷ trọng mục tiêu và đề xuất cân bằng lại.'],
 drift:['Ngưỡng lệch tỷ trọng','Mức chênh lệch giữa tỷ trọng hiện tại và tỷ trọng mục tiêu để hệ thống bắt đầu xem xét điều chỉnh. Ngưỡng nhỏ có thể dẫn đến đề xuất thường xuyên hơn.'],
 rebalance:['Đề xuất cân bằng lại','Hệ thống so sánh tỷ trọng hiện tại với kế hoạch đã lưu khi có dữ liệu giá phù hợp. Nếu chênh lệch vượt ngưỡng và đáp ứng giới hạn giao dịch, hệ thống sẽ hiển thị phương án tham khảo. Không tự đặt lệnh.'],
 rotation:['Sức mạnh ngành','Biểu đồ hiển thị vị trí tương đối của các ngành theo hiệu suất 5 và 20 phiên so với nhóm cổ phiếu đủ dữ liệu. Rê chuột hoặc chọn một ngành để xem quỹ đạo và số liệu. Đây không phải tín hiệu dự báo.']
};
const pop=document.createElement('div');pop.id='portfolio-help-popover';pop.className='portfolio-help-popover';pop.setAttribute('role','dialog');pop.setAttribute('aria-modal','false');pop.setAttribute('aria-labelledby','portfolio-help-title');pop.hidden=true;
const h=document.createElement('strong');h.id='portfolio-help-title';
const p=document.createElement('p');
const close=document.createElement('button');close.type='button';close.className='portfolio-help-close';close.textContent='Đóng';close.setAttribute('aria-label','Đóng giải thích');
pop.append(h,p,close);root.appendChild(pop);
let active=null;
const hide=(restore=false)=>{pop.hidden=true;if(active){active.setAttribute('aria-expanded','false');if(restore)active.focus();}active=null;};
root.addEventListener('click',e=>{
 const b=e.target.closest?.('[data-portfolio-help]');
 if(!b){if(!pop.hidden&&!pop.contains(e.target))hide();return;}
 const data=copy[b.dataset.portfolioHelp];if(!data)return;
 if(active===b&&!pop.hidden){hide(true);return;}
 hide();active=b;h.textContent=data[0];p.textContent=data[1];b.setAttribute('aria-expanded','true');pop.hidden=false;
 const bounds=b.getBoundingClientRect(),parent=root.getBoundingClientRect();
 pop.style.top=(bounds.bottom-parent.top+9)+'px';pop.style.left=Math.max(12,Math.min(bounds.left-parent.left-5,Math.max(12,parent.width-335)))+'px';
});
close.addEventListener('click',()=>hide(true));
document.addEventListener('keydown',e=>{if(e.key==='Escape'&&!pop.hidden)hide(true);});
})();