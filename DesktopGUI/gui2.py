# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file '.\gui2.ui'
#
# Created by: PyQt5 UI code generator 5.15.11
#
# WARNING: Any manual changes made to this file will be lost when pyuic5 is
# run again.  Do not edit this file unless you know what you are doing.


from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtWidgets import QApplication, QWidget, QVBoxLayout, QListWidget, QListWidgetItem
from PyQt5.QtGui import QStandardItemModel,QStandardItem
from PyQt5.QtCore import Qt,QModelIndex
from bs4 import BeautifulSoup
import requests
import json


f = open("setup.json", "r")
setup = json.load(f)
f.close()
base_url = setup["gogoanime_main"]



class Ui_MainWindow(object):
    def setupUi(self, MainWindow):
        MainWindow.setObjectName("MainWindow")
        MainWindow.resize(644, 665)
        self.centralwidget = QtWidgets.QWidget(MainWindow)
        self.centralwidget.setObjectName("centralwidget")
        self.Heading = QtWidgets.QLabel(self.centralwidget)
        self.Heading.setGeometry(QtCore.QRect(10, 10, 491, 51))
        font = QtGui.QFont()
        font.setBold(True)
        font.setPointSize(20)
        self.Heading.setFont(font)
        self.Heading.setObjectName("Heading")
        self.downloadTypeLabel = QtWidgets.QLabel(self.centralwidget)
        self.downloadTypeLabel.setGeometry(QtCore.QRect(10, 70, 171, 31))
        font = QtGui.QFont()
        font.setPointSize(14)
        font.setBold(True)
        font.setWeight(75)
        self.downloadTypeLabel.setFont(font)
        self.downloadTypeLabel.setObjectName("downloadTypeLabel")
        self.singleRadioBtn = QtWidgets.QRadioButton(self.centralwidget)
        self.singleRadioBtn.setGeometry(QtCore.QRect(40, 120, 151, 17))
        font = QtGui.QFont()
        font.setPointSize(9)
        self.singleRadioBtn.setFont(font)
        self.singleRadioBtn.setObjectName("singleRadioBtn")
        self.batchRadioBtn = QtWidgets.QRadioButton(self.centralwidget)
        self.batchRadioBtn.setGeometry(QtCore.QRect(40, 150, 131, 17))
        font = QtGui.QFont()
        font.setPointSize(9)
        self.batchRadioBtn.setFont(font)
        self.batchRadioBtn.setObjectName("batchRadioBtn")
        self.SearchLabel = QtWidgets.QLabel(self.centralwidget)
        self.SearchLabel.setGeometry(QtCore.QRect(10, 180, 221, 41))
        font = QtGui.QFont()
        font.setPointSize(8)
        font.setBold(True)
        font.setWeight(75)
        self.SearchLabel.setFont(font)
        self.SearchLabel.setObjectName("SearchLabel")
        self.SearchInput = QtWidgets.QLineEdit(self.centralwidget)
        self.SearchInput.setGeometry(QtCore.QRect(10, 210, 251, 31))
        self.SearchInput.setClearButtonEnabled(True)
        self.SearchInput.setObjectName("SearchInput")
        self.listWidget = QtWidgets.QListWidget(self.centralwidget)
        self.listWidget.setGeometry(QtCore.QRect(10, 290, 371, 301))
        self.listWidget.setObjectName("listWidget")
        self.SearchLabel_2 = QtWidgets.QLabel(self.centralwidget)
        self.SearchLabel_2.setGeometry(QtCore.QRect(10, 260, 221, 41))
        font = QtGui.QFont()
        font.setPointSize(8)
        font.setBold(True)
        font.setWeight(75)
        self.SearchLabel_2.setFont(font)
        self.SearchLabel_2.setObjectName("SearchLabel_2")
        self.searchButton = QtWidgets.QPushButton(self.centralwidget)
        self.searchButton.setGeometry(QtCore.QRect(270, 210, 111, 31))
        self.searchButton.setObjectName("pushButton")
        MainWindow.setCentralWidget(self.centralwidget)
        self.menubar = QtWidgets.QMenuBar(MainWindow)
        self.menubar.setGeometry(QtCore.QRect(0, 0, 644, 21))
        self.menubar.setObjectName("menubar")
        self.menuFile = QtWidgets.QMenu(self.menubar)
        self.menuFile.setObjectName("menuFile")
        self.menuNew = QtWidgets.QMenu(self.menuFile)
        self.menuNew.setObjectName("menuNew")
        self.menuDownload = QtWidgets.QMenu(self.menubar)
        self.menuDownload.setObjectName("menuDownload")
        self.menuView = QtWidgets.QMenu(self.menubar)
        self.menuView.setObjectName("menuView")
        MainWindow.setMenuBar(self.menubar)
        self.statusbar = QtWidgets.QStatusBar(MainWindow)
        self.statusbar.setObjectName("statusbar")
        MainWindow.setStatusBar(self.statusbar)
        self.actionSingle = QtWidgets.QAction(MainWindow)
        self.actionSingle.setObjectName("actionSingle")
        self.actionSave_As = QtWidgets.QAction(MainWindow)
        self.actionSave_As.setObjectName("actionSave_As")
        self.actionLoad_List = QtWidgets.QAction(MainWindow)
        self.actionLoad_List.setObjectName("actionLoad_List")
        self.actionSingle_2 = QtWidgets.QAction(MainWindow)
        self.actionSingle_2.setObjectName("actionSingle_2")
        self.actionBatch = QtWidgets.QAction(MainWindow)
        self.actionBatch.setObjectName("actionBatch")
        self.actionDownload_Quality = QtWidgets.QAction(MainWindow)
        self.actionDownload_Quality.setObjectName("actionDownload_Quality")
        self.actionSave_BatchList = QtWidgets.QAction(MainWindow)
        self.actionSave_BatchList.setObjectName("actionSave_BatchList")
        self.actionLoad_BatchList = QtWidgets.QAction(MainWindow)
        self.actionLoad_BatchList.setObjectName("actionLoad_BatchList")
        self.menuNew.addAction(self.actionSingle)
        self.menuFile.addAction(self.menuNew.menuAction())
        self.menuFile.addAction(self.actionSave_As)
        self.menuFile.addAction(self.actionLoad_List)
        self.menuDownload.addAction(self.actionDownload_Quality)
        self.menuView.addAction(self.actionSave_BatchList)
        self.menuView.addAction(self.actionLoad_BatchList)
        self.menubar.addAction(self.menuFile.menuAction())
        self.menubar.addAction(self.menuDownload.menuAction())
        self.menubar.addAction(self.menuView.menuAction())

        # Warning Label
        self.warningLabel = QtWidgets.QLabel(self.centralwidget)
        self.warningLabel.setGeometry(QtCore.QRect(10, 60, 491, 30))
        self.warningLabel.setObjectName("warningLabel")
        self.warningLabel.setStyleSheet("color: red; font-size: 12px;")
        self.warningLabel.setText("")  # Initially empty
        self.warningLabel.setVisible(False)  # Hidden by default


        self.retranslateUi(MainWindow)
        QtCore.QMetaObject.connectSlotsByName(MainWindow)

        self.searchButton.clicked.connect( self.perform_search)


    async def perform_search(self):
        print("Search")

        async def update_list_widget(links):
            """Clear the list and add new links."""
            self.listWidget.clear()
            for link in links:
                item = QListWidgetItem(link)
                self.listWidget.addItem(item)

        async def get_names(response):
            titles = response.find("ul", {"class": "items"}).find_all("li")
            names = []
            for i in titles:
                name = i.p.a.get("title")
                url = i.p.a.get("href")
                names.append([name, url])
            return names

        async def search():
            """
            Search for anime and return download links for selected episodes.
            Returns:
                List[Dict[str, str]]: List of dictionaries containing episode information and download links.
            """
            # while True:
            name = self.SearchInput.text()
            print(f"Searching {name}")
            response = BeautifulSoup(requests.get(f"{base_url}/search.html?keyword={name}").text, "html.parser")

            try:
                print(1)
                pages = response.find("ul", {"class": "pagination-list"}).find_all("li")
                animes = [anime for page in pages for anime in get_names(BeautifulSoup(requests.get(f"{base_url}/search.html{page.a.get('href')}").text,"html.parser"))]
            except AttributeError:
                print(2)
                animes = get_names(response)

            print(animes[0], animes[0][0])

            if not animes:
                print("No results found. try again")
                self.warningLabel.setText("No results found. Try again.")
                self.warningLabel.setVisible(True)


            self.listWidget.clear()
            for anime_link in animes:
                item = QListWidgetItem(anime_link[0])
                self.listWidget.addItem(item)

                await resize_list_widget()

        async def resize_list_widget():
            item_count = self.listWidget.count()
            item_height = self.listWidget.sizeHintForRow(0)

            max_display_items = 15
            visible_items = min(item_count, max_display_items)
            total_height = visible_items * item_height + 10 # 10 px padding

            self.listWidget.setFixedHeight(total_height)



            # while True:
            #     try:
            #         selected_anime = int(input(f"{Fore.YELLOW}Select anime number: {Style.RESET_ALL}")) - 1
            #         if 0 <= selected_anime < len(animes):
            #             break
            #         raise ValueError
            #     except ValueError:
            #         print(f"{Fore.RED}Invalid selection. Try again.{Style.RESET_ALL}")
            #
            # return create_links(animes[selected_anime])

        await search()

    def retranslateUi(self, MainWindow):
        _translate = QtCore.QCoreApplication.translate
        MainWindow.setWindowTitle(_translate("MainWindow", "MainWindow"))
        self.Heading.setText(_translate("MainWindow", "AnimDownloader"))
        self.downloadTypeLabel.setText(_translate("MainWindow", "Download Type:"))
        self.singleRadioBtn.setText(_translate("MainWindow", "Single"))
        self.batchRadioBtn.setText(_translate("MainWindow", "Batch"))
        self.SearchLabel.setText(_translate("MainWindow", "Enter Anime:"))
        self.SearchInput.setToolTip(_translate("MainWindow", "Search the anime you wnt to download"))
        self.SearchInput.setPlaceholderText(_translate("MainWindow", "Search"))
        self.SearchLabel_2.setText(_translate("MainWindow", "Search Results:"))
        self.searchButton.setText(_translate("MainWindow", "Search"))
        self.menuFile.setTitle(_translate("MainWindow", "File"))
        self.menuNew.setTitle(_translate("MainWindow", "New"))
        self.menuDownload.setTitle(_translate("MainWindow", "Settings"))
        self.menuView.setTitle(_translate("MainWindow", "Batch List"))
        self.actionSingle.setText(_translate("MainWindow", "Single"))
        self.actionSave_As.setText(_translate("MainWindow", "Save As..."))
        self.actionLoad_List.setText(_translate("MainWindow", "Load List"))
        self.actionSingle_2.setText(_translate("MainWindow", "Single"))
        self.actionBatch.setText(_translate("MainWindow", "Batch"))
        self.actionDownload_Quality.setText(_translate("MainWindow", "Download Quality"))
        self.actionSave_BatchList.setText(_translate("MainWindow", "Save BatchList"))
        self.actionLoad_BatchList.setText(_translate("MainWindow", "Load BatchList"))


if __name__ == "__main__":
    import sys
    app = QtWidgets.QApplication(sys.argv)
    MainWindow = QtWidgets.QMainWindow()
    ui = Ui_MainWindow()
    ui.setupUi(MainWindow)
    MainWindow.show()
    sys.exit(app.exec_())