"""Plain .xlsx output: detailed rows, years across columns, no comments or notes."""
from io import BytesIO
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from .data_validator import validate_period
from .metrics import decorate

NUMBER='#,##0.00;(#,##0.00);"-"'
INTEGER='#,##0;(#,##0);"-"'

class ExcelBuilder:
    def build_bytes(self,data,years=None,report_ids=None):
        data=decorate(data)
        years=validate_period(data,years or data.get('periods',data['years']),report_ids)
        sections=[s for s in data['sections'] if report_ids is None or s['id'] in report_ids]
        workbook=Workbook();workbook.remove(workbook.active)
        groups=[('BCTC',[s for s in sections if s['id'] not in ('ratios','derived_ratios','notes')]),('Chi_so',[s for s in sections if s['id'] in ('ratios','derived_ratios')]),('Thuyet_minh',[s for s in sections if s['id']=='notes'])]
        edge=Side(style='thin',color='DDDDDD')
        for sheet_name,reports in groups:
            if not reports:continue
            ws=workbook.create_sheet(sheet_name);ws.sheet_view.showGridLines=False;ws.freeze_panes='B5'
            ws.append([f"{data['symbol']} - {data.get('name',data['symbol'])}"])
            ws.append(['Đơn vị: triệu đồng' if sheet_name!='Chi_so' else 'CHỈ SỐ TÀI CHÍNH'])
            ws.append([]);ws.append(['CHỈ TIÊU',*[f"Q{str(p)[-1]}/{str(p)[:4]}" if '-Q' in str(p) else p for p in years]])
            ws.merge_cells(start_row=1,start_column=1,end_row=1,end_column=len(years)+1)
            ws.merge_cells(start_row=2,start_column=1,end_row=2,end_column=len(years)+1)
            for section in reports:
                ws.append([section['name'].upper()]);section_row=ws.max_row
                for cell in ws[section_row]:cell.fill=PatternFill('solid',fgColor='EDEDED');cell.font=Font(name='Arial',size=11,bold=True)
                for row in section['rows']:
                    unit=row.get('unit','');label=row['label']
                    if unit and (unit!='triệu đồng' or section['id'] in ('ratios','derived_ratios')) and unit.lower() not in label.lower():label+=f' ({unit})'
                    ws.append([label,*[row['values'].get(str(y)) for y in years]])
                    for cell in ws[ws.max_row]:
                        cell.font=Font(name='Arial',size=11,bold=bool(row.get('bold')))
                        cell.border=Border(left=edge,right=edge,top=edge,bottom=edge)
                        cell.alignment=Alignment(vertical='center',horizontal='left' if cell.column==1 else 'right',wrap_text=cell.column==1)
                        if cell.column>1:cell.number_format=INTEGER if unit in ('đồng/cp','cổ phiếu') else NUMBER
                    ws.cell(ws.max_row,1).data_type='s'
                    ws.row_dimensions[ws.max_row].height=max(22,((len(label)+77)//78)*17)
            for row in ws:
                for cell in row:
                    if cell.row<=4:cell.font=Font(name='Arial',size=11,bold=cell.row in (1,4))
            for cell in ws[4]:cell.fill=PatternFill('solid',fgColor='E5E5E5');cell.alignment=Alignment(horizontal='center',vertical='center')
            ws.column_dimensions['A'].width=82
            for col in range(2,len(years)+2):ws.column_dimensions[get_column_letter(col)].width=20
            ws.row_dimensions[1].height=28;ws.row_dimensions[4].height=25
            ws.print_title_rows='1:4';ws.sheet_properties.pageSetUpPr.fitToPage=True
            ws.page_setup.orientation='landscape';ws.page_setup.paperSize=ws.PAPERSIZE_A4;ws.page_setup.fitToWidth=1;ws.page_setup.fitToHeight=0
        if not workbook.worksheets:raise ValueError('Chưa chọn báo cáo có dữ liệu.')
        output=BytesIO();workbook.save(output);return output.getvalue()

    def build(self,financial_data,output_path,years=None,report_ids=None):
        from pathlib import Path
        Path(output_path).write_bytes(self.build_bytes(financial_data,years,report_ids));return str(output_path)
