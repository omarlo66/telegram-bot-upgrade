import xlsxwriter


class ExcelWriter:
    def __init__(self, filename: str):
        self.filename = filename

    def write(self, headers: list[str], rows: list[list]):
        workbook = xlsxwriter.Workbook(self.filename)
        worksheet = workbook.add_worksheet()

        bold = workbook.add_format({'bold': True})

        # money = workbook.add_format({'num_format': '$#,##0'})

        for index, header in enumerate(headers):
            worksheet.write(0, index, header, bold)

        for row, row_data in enumerate(rows):
            for col, col_data in enumerate(row_data):
                worksheet.write(row + 1, col, col_data)

        worksheet.autofit()
        workbook.close()
