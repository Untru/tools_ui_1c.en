#!/usr/bin/env python3
"""
Hybrid approach: 1C-specific dictionary + Google Translate fallback.

Usage:
  python fix_hybrid.py --analyze          # Show what would be fixed (first 200)
  python fix_hybrid.py --fix-dict         # Fix common-camelcase_en.dict
  python fix_hybrid.py --fix-trans        # Fix _en.trans files
  python fix_hybrid.py --fix-all          # Fix everything
  python fix_hybrid.py --stats            # Just show statistics
"""

import os
import re
import sys
import json
import time
from pathlib import Path
from collections import defaultdict

# ── 1C-specific dictionary ────────────────────────────────────────────────
# Maps Russian words (all grammatical forms) to English 1C-standard terms.
# These override Google Translate for domain-specific accuracy.

DICT_1C = {
    # ─── Core platform types ───
    "Массив": "Array", "Массива": "Array", "Массивов": "Arrays",
    "Структура": "Structure", "Структуру": "Structure", "Структуры": "Structure",
    "Соответствие": "Map", "Соответствия": "Map",
    "Список": "List", "Списка": "List", "Списков": "Lists", "Списке": "List",
    "Таблица": "Table", "Таблицу": "Table", "Таблицы": "Table", "Таблиц": "Tables",
    "Дерево": "Tree", "Дерева": "Tree",
    "Значений": "Values", "Значения": "Value", "Значение": "Value", "Значению": "Value",
    "Значениям": "Values", "Значением": "Value",
    "Строка": "String", "Строки": "String", "Строку": "String", "Строке": "String",
    "Строкой": "String", "Строк": "Strings",
    "Число": "Number", "Числа": "Number", "Числовых": "Numeric",
    "Булево": "Boolean", "Булевого": "Boolean",
    "Дата": "Date", "Даты": "Date", "Дату": "Date", "Датой": "Date",
    "Ссылка": "Ref", "Ссылки": "Ref", "Ссылку": "Ref", "Ссылок": "Refs",
    "Ссылке": "Ref", "Ссылкой": "Ref",

    # ─── Metadata objects ───
    "Справочник": "Catalog", "Справочника": "Catalog", "Справочников": "Catalogs",
    "Справочники": "Catalogs", "Справочнику": "Catalog", "Справочнике": "Catalog",
    "Документ": "Document", "Документа": "Document", "Документов": "Documents",
    "Документы": "Documents", "Документу": "Document", "Документе": "Document",
    "Регистр": "Register", "Регистра": "Register", "Регистров": "Registers",
    "Регистры": "Registers", "Регистру": "Register",
    "Накопления": "Accumulation", "Накопление": "Accumulation",
    "Сведений": "Information", "Сведения": "Information",
    "Бухгалтерии": "Accounting", "Бухгалтерия": "Accounting",
    "Расчета": "Calculation", "Расчет": "Calculation", "Расчетов": "Calculations",
    "Перечисление": "Enum", "Перечисления": "Enum", "Перечислений": "Enums",
    "Перечислению": "Enum",
    "Обработка": "DataProcessor", "Обработки": "DataProcessor", "Обработку": "DataProcessor",
    "Обработке": "DataProcessor", "Обработок": "DataProcessors",
    "Отчет": "Report", "Отчета": "Report", "Отчетов": "Reports",
    "Отчеты": "Reports", "Отчете": "Report",
    "Константа": "Constant", "Константы": "Constants", "Констант": "Constants",
    "Константу": "Constant",
    "План": "Plan", "Плана": "Plan", "Планов": "Plans",
    "Обмена": "Exchange", "Обмен": "Exchange", "Обменов": "Exchanges",
    "Видов": "Types", "Виды": "Types", "Вида": "Type", "Вид": "Type",
    "Характеристик": "Characteristics", "Характеристики": "Characteristics",
    "Счетов": "Accounts", "Счет": "Account", "Счета": "Account",
    "Подсистема": "Subsystem", "Подсистемы": "Subsystem",

    # ─── Register specifics ───
    "Движения": "Records", "Движений": "Records", "Движение": "Record",
    "Измерения": "Dimensions", "Измерений": "Dimensions", "Измерение": "Dimension",
    "Ресурсы": "Resources", "Ресурсов": "Resources", "Ресурса": "Resource",
    "Ресурс": "Resource",
    "Реквизит": "Attribute", "Реквизита": "Attribute", "Реквизитов": "Attributes",
    "Реквизиты": "Attributes", "Реквизиту": "Attribute",
    "Измерению": "Dimension",
    "Итог": "Total", "Итога": "Total", "Итогов": "Totals", "Итоги": "Totals",
    "Остаток": "Balance", "Остатка": "Balance", "Остатков": "Balances",
    "Оборот": "Turnover", "Оборота": "Turnover", "Оборотов": "Turnovers",

    # ─── Forms and UI ───
    "Форма": "Form", "Формы": "Form", "Форме": "Form", "Форм": "Forms",
    "Форму": "Form",
    "Элемент": "Item", "Элемента": "Item", "Элементов": "Items",
    "Элементы": "Items", "Элементу": "Item",
    "Команда": "Command", "Команды": "Command", "Команд": "Commands",
    "Команде": "Command", "Команду": "Command",
    "Кнопка": "Button", "Кнопки": "Button", "Кнопку": "Button",
    "Поле": "Field", "Поля": "Field", "Полей": "Fields", "Полю": "Field",
    "Группа": "Group", "Группы": "Group", "Групп": "Groups",
    "Группу": "Group", "Группе": "Group",
    "Надпись": "Label", "Надписи": "Label",
    "Таблица": "Table",
    "Декорация": "Decoration", "Декорации": "Decoration",
    "Страница": "Page", "Страницы": "Page", "Страниц": "Pages",

    # ─── Common programming terms ───
    "Объект": "Object", "Объекта": "Object", "Объектов": "Objects",
    "Объекты": "Objects", "Объекту": "Object", "Объекте": "Object",
    "Менеджер": "Manager", "Менеджера": "Manager", "Менеджеров": "Managers",
    "Модуль": "Module", "Модуля": "Module", "Модулей": "Modules",
    "Метаданные": "Metadata", "Метаданных": "Metadata", "Метаданными": "Metadata",
    "Тип": "Type", "Типа": "Type", "Типов": "Types", "Типу": "Type",
    "Типе": "Type", "Типы": "Types",
    "Параметр": "Parameter", "Параметра": "Parameter", "Параметров": "Parameters",
    "Параметры": "Parameters", "Параметру": "Parameter",
    "Свойство": "Property", "Свойства": "Property", "Свойств": "Properties",
    "Свойствам": "Properties",
    "Метод": "Method", "Метода": "Method", "Методов": "Methods",
    "Функция": "Function", "Функции": "Function", "Функций": "Functions",
    "Процедура": "Procedure", "Процедуры": "Procedure", "Процедур": "Procedures",
    "Переменная": "Variable", "Переменной": "Variable", "Переменных": "Variables",
    "Переменные": "Variables", "Переменную": "Variable",
    "Коллекция": "Collection", "Коллекции": "Collection", "Коллекций": "Collections",
    "Ключ": "Key", "Ключа": "Key", "Ключей": "Keys", "Ключом": "Key",
    "Индекс": "Index", "Индекса": "Index",
    "Запись": "Record", "Записи": "Record", "Записей": "Records",
    "Записью": "Record",
    "Набор": "Set", "Набора": "Set", "Наборов": "Sets", "Наборы": "Sets",
    "Выборка": "Selection", "Выборки": "Selection", "Выборку": "Selection",

    # ─── Common actions/verbs ───
    "Получить": "Get", "Получение": "Get", "Получения": "Getting",
    "Установить": "Set", "Установка": "Set", "Установки": "Settings",
    "Установку": "Setting",
    "Создать": "Create", "Создание": "Creation", "Создания": "Creation",
    "Удалить": "Delete", "Удаление": "Deletion", "Удаления": "Deletion",
    "Удалению": "Deletion", "Удаляемый": "Deleted",
    "Изменить": "Change", "Изменение": "Change", "Изменения": "Changes",
    "Изменении": "Change", "Изменений": "Changes",
    "Добавить": "Add", "Добавление": "Adding",
    "Записать": "Write", "Записей": "Records",
    "Прочитать": "Read", "Чтение": "Reading", "Чтения": "Reading",
    "Выполнить": "Execute", "Выполнение": "Execution", "Выполнения": "Execution",
    "Выполнением": "Execution", "Выполнять": "Execute",
    "Загрузить": "Load", "Загрузка": "Loading", "Загрузки": "Loading",
    "Загруженные": "Loaded",
    "Выгрузить": "Unload", "Выгрузка": "Unload", "Выгрузки": "Unload",
    "Выгрузкой": "Unload", "Выгружать": "Unload",
    "Обновить": "Update", "Обновление": "Update", "Обновления": "Update",
    "Сохранить": "Save", "Сохранение": "Save", "Сохранения": "Saving",
    "Копировать": "Copy", "Копирование": "Copy", "Копирования": "Copy",
    "Копии": "Copy",
    "Поиск": "Search", "Поиска": "Search", "Поиске": "Search",
    "Найти": "Find", "Нахождение": "Finding",
    "Заполнить": "Fill", "Заполнение": "Fill", "Заполнения": "Fill",
    "Заполнен": "Filled",
    "Формирование": "Generate", "Формирования": "Generation",
    "Вычислить": "Calculate", "Вычисление": "Calculation", "Вычислять": "Calculate",
    "Вычисляемое": "Calculated", "Вычисляемого": "Calculated",
    "Проверить": "Check", "Проверка": "Check", "Проверки": "Check",
    "Проверку": "Check",
    "Сортировать": "Sort", "Сортировка": "Sort", "Сортировки": "Sort",
    "Отобрать": "Filter", "Отбор": "Filter", "Отбора": "Filter",
    "Отборы": "Filters",
    "Группировать": "Group", "Группировка": "Grouping", "Группировки": "Grouping",
    "Сравнить": "Compare", "Сравнение": "Comparison", "Сравнения": "Comparison",
    "Разобрать": "Parse", "Собрать": "Build",
    "Описание": "Description", "Описания": "Description", "Описаний": "Descriptions",
    "Описании": "Description",

    # ─── Notifications / Events ───
    "Оповещение": "Notification", "Оповещения": "Notification",
    "Оповещений": "Notifications", "Оповещению": "Notification",
    "Подписка": "Subscription", "Подписки": "Subscription",
    "Подписок": "Subscriptions",
    "Событие": "Event", "События": "Event", "Событий": "Events",
    "Обработчик": "Handler", "Обработчика": "Handler", "Обработчиков": "Handlers",
    "Обработчики": "Handlers",

    # ─── Configuration / Extension ───
    "Конфигурация": "Configuration", "Конфигурации": "Configuration",
    "Конфигурацию": "Configuration",
    "Расширение": "Extension", "Расширения": "Extension",
    "Расширений": "Extensions", "Расширенная": "Extended",
    "Расширенное": "Extended", "Расширенный": "Extended",
    "Хранилище": "Storage", "Хранилища": "Storage",
    "Хранилищ": "Storages", "Хранимых": "Stored",

    # ─── Data composition (СКД) ───
    "Компоновка": "Composition", "Компоновки": "Composition",
    "Компоновщик": "Composer", "Компоновщика": "Composer",
    "Данных": "Data", "Данные": "Data", "Данными": "Data",
    "Схема": "Schema", "Схемы": "Schema", "Схему": "Schema",
    "Макет": "Template", "Макета": "Template", "Макетов": "Templates",
    "Макеты": "Templates",
    "Вариант": "Variant", "Варианта": "Variant", "Вариантов": "Variants",
    "Варианты": "Variants",
    "Настройка": "Setting", "Настройки": "Settings", "Настроек": "Settings",
    "Настройку": "Setting", "Настройках": "Settings", "Настроить": "Configure",

    # ─── Scheduled/Background jobs ───
    "Задание": "Job", "Задания": "Job", "Заданий": "Jobs", "Заданием": "Job",
    "Регламентное": "Scheduled", "Регламентных": "Scheduled",
    "Регламентный": "Scheduled", "Регламентного": "Scheduled",
    "Фоновое": "Background", "Фоновых": "Background", "Фонового": "Background",
    "Фона": "Background",

    # ─── Sessions / Users ───
    "Сеанс": "Session", "Сеанса": "Session", "Сеансов": "Sessions",
    "Пользователь": "User", "Пользователя": "User",
    "Пользователей": "Users", "Пользователю": "User",
    "Пользовательские": "Custom", "Пользовательское": "Custom",
    "Пользовательского": "Custom", "Пользовательских": "Custom",

    # ─── Queries ───
    "Запрос": "Query", "Запроса": "Query", "Запросов": "Queries",
    "Запросы": "Queries",
    "Результат": "Result", "Результата": "Result", "Результатов": "Results",
    "Временные": "Temporary", "Временная": "Temporary", "Временного": "Temporary",
    "Временный": "Temporary", "Временных": "Temporary",

    # ─── XML / JSON / HTTP ───
    "Чтение": "Reading", "Запись": "Writing",
    "Сериализация": "Serialization", "Десериализация": "Deserialization",
    "Кодировка": "Encoding", "Кодировки": "Encoding",
    "Соединение": "Connection", "Соединения": "Connection",
    "Соединений": "Connections",
    "Подключение": "Connection", "Подключения": "Connection",
    "Аутентификация": "Authentication", "Аутентификации": "Authentication",
    "Сертификат": "Certificate", "Сертификата": "Certificate",
    "Сертификатов": "Certificates", "Сертификаты": "Certificates",

    # ─── Common adjectives/prepositions ───
    "Новый": "New", "Нового": "New", "Новая": "New", "Новое": "New",
    "Новые": "New", "Новую": "New",
    "Текущий": "Current", "Текущая": "Current", "Текущее": "Current",
    "Текущего": "Current", "Текущей": "Current", "Текущие": "Current",
    "Старый": "Old", "Старого": "Old",
    "Основной": "Main", "Основная": "Main", "Основное": "Main",
    "Основного": "Main", "Основных": "Main", "Основные": "Main",
    "Внешний": "External", "Внешняя": "External", "Внешнее": "External",
    "Внешнего": "External", "Внешней": "External", "Внешних": "External",
    "Внутренний": "Internal", "Внутренняя": "Internal",
    "Полный": "Full", "Полная": "Full", "Полное": "Full",
    "Полного": "Full", "Полная": "Full",
    "Активный": "Active", "Активная": "Active", "Активное": "Active",
    "Активна": "Active", "Активно": "Active",
    "Доступный": "Available", "Доступные": "Available", "Доступных": "Available",
    "Доступна": "Available",
    "Максимальный": "Maximum", "Максимального": "Maximum",
    "Минимальный": "Minimum", "Минимального": "Minimum",
    "Стандартное": "Standard", "Стандартная": "Standard", "Стандартный": "Standard",
    "Фиксированный": "Fixed", "Фиксированная": "Fixed", "Фиксированное": "Fixed",
    "Фиксированного": "Fixed",
    "Табличный": "Tabular", "Табличного": "Tabular", "Табличном": "Tabular",
    "Табличную": "Tabular", "Табличным": "Tabular",
    "Глобальный": "Global", "Глобальная": "Global", "Глобальное": "Global",
    "Глобальном": "Global", "Глобальных": "Global",
    "Локальный": "Local", "Локальная": "Local", "Локальное": "Local",
    "Программный": "Program", "Программного": "Program",
    "Оригинальный": "Original", "Оригинальная": "Original",
    "Вложенный": "Nested", "Вложенная": "Nested",
    "Защищенное": "Secure", "Защищенного": "Secure",
    "Разрешенный": "Allowed",
    "Сгенерированный": "Generated",
    "Выделенный": "Selected",
    "Исполняемый": "Executable",
    "Рабочий": "Working", "Рабочая": "Working",
    "Клиентского": "Client", "Клиентское": "Client",
    "Почтовый": "Mail", "Почтового": "Mail", "Почтовая": "Mail",
    "Кадровый": "HR",
    "Форматированного": "Formatted", "Форматированный": "Formatted",
    "Удостоверяющих": "Certifying",

    # ─── Common nouns ───
    "Имя": "Name", "Имени": "Name",
    "Код": "Code", "Кода": "Code", "Кодов": "Codes",
    "Файл": "File", "Файла": "File", "Файлов": "Files", "Файлами": "Files",
    "Каталог": "Directory", "Каталога": "Directory",
    "Путь": "Path", "Пути": "Path",
    "Адрес": "Address", "Адреса": "Address",
    "Версия": "Version", "Версии": "Version",
    "Сервер": "Server", "Сервера": "Server", "Серверов": "Servers",
    "Сервере": "Server",
    "Клиент": "Client", "Клиента": "Client",
    "База": "Database", "Базы": "Database", "Базу": "Database", "Базе": "Database",
    "Область": "Area", "Области": "Area", "Областей": "Areas",
    "Пароль": "Password", "Пароля": "Password", "Паролей": "Passwords",
    "Роль": "Role", "Роли": "Role", "Ролей": "Roles",
    "Право": "Right", "Права": "Right", "Прав": "Rights",
    "Доступ": "Access", "Доступа": "Access",
    "Журнал": "Log", "Журнала": "Log", "Журналов": "Logs",
    "Ошибка": "Error", "Ошибки": "Error", "Ошибок": "Errors", "Ошибке": "Error",
    "Предупреждение": "Warning", "Предупреждения": "Warnings",
    "Сообщение": "Message", "Сообщения": "Message", "Сообщить": "Message",
    "Режим": "Mode", "Режима": "Mode", "Режиме": "Mode",
    "Способ": "Method", "Способа": "Method",
    "Представление": "Presentation", "Представления": "Presentation",
    "Представлений": "Presentations",
    "Заголовок": "Title", "Заголовка": "Title", "Заголовков": "Titles",
    "Система": "System", "Системы": "System", "Системе": "System",
    "Системных": "System", "Системная": "System",
    "Интерфейс": "Interface", "Интерфейса": "Interface",
    "Окно": "Window", "Окна": "Window", "Окон": "Windows",
    "Колонка": "Column", "Колонки": "Column", "Колонок": "Columns",
    "Шаблон": "Template", "Шаблоны": "Templates",
    "Алгоритм": "Algorithm", "Алгоритма": "Algorithm", "Алгоритмов": "Algorithms",
    "Контейнер": "Container", "Контейнера": "Container",
    "Буфер": "Buffer", "Буфера": "Buffer",
    "Профиль": "Profile", "Профиля": "Profile",
    "Пакет": "Package", "Пакета": "Package",
    "Компонент": "Component", "Компонента": "Component",
    "Сервис": "Service", "Сервиса": "Service",
    "Консоль": "Console", "Консоли": "Console",
    "Прогресс": "Progress", "Прогресса": "Progress",
    "Архив": "Archive", "Архива": "Archive",
    "Линия": "Line", "Линии": "Line",
    "Ячейка": "Cell", "Ячейки": "Cell", "Ячеек": "Cells",
    "Точка": "Point", "Точки": "Point", "Точек": "Points",
    "Редактор": "Editor", "Редактора": "Editor",
    "Построитель": "Builder", "Построителя": "Builder",
    "Центр": "Center", "Центра": "Center", "Центров": "Centers",
    "Состав": "Composition", "Состава": "Composition",
    "Копия": "Copy",
    "Куб": "Cube",

    # ─── Abstract concepts ───
    "Администрирование": "Administration", "Администрирования": "Administration",
    "Завершение": "Completion", "Завершении": "Completion", "Завершения": "Completion",
    "Взаимодействие": "Interaction", "Взаимодействия": "Interaction",
    "Управление": "Management", "Управления": "Management",
    "Регистрация": "Registration", "Регистрации": "Registration",
    "Регистрацию": "Registration",
    "Инициализация": "Initialization", "Инициализации": "Initialization",
    "Преобразование": "Conversion", "Преобразования": "Conversion",
    "Идентичность": "Identity", "Идентичности": "Identity",
    "Лицензирование": "Licensing", "Лицензирования": "Licensing",
    "Криптография": "Cryptography", "Криптографии": "Cryptography",
    "Восстановление": "Recovery", "Восстановления": "Recovery",
    "Распознавание": "Recognition", "Распознавания": "Recognition",
    "Интеграция": "Integration", "Интеграции": "Integration",
    "Сжатие": "Compression", "Сжатия": "Compression",
    "Анализ": "Analysis", "Анализа": "Analysis",
    "Продолжение": "Continuation",
    "Упорядочивание": "Ordering", "Упорядочивания": "Ordering",
    "Сканирование": "Scanning", "Сканирования": "Scanning",
    "Потребление": "Consumption", "Потребления": "Consumption",
    "Ограничение": "Restriction", "Ограничения": "Restrictions",
    "Разрешение": "Permission", "Разрешения": "Permissions",
    "Назначение": "Assignment", "Назначения": "Assignment",
    "Размещение": "Placement", "Размещения": "Placement",
    "Разделение": "Separation", "Разделения": "Separation",
    "Применение": "Application", "Применения": "Application",
    "Замена": "Replacement", "Замены": "Replacement",
    "Состояние": "State", "Состояния": "State",
    "Положение": "Position", "Положения": "Position",
    "Перемещение": "Moving",
    "Ожидание": "Waiting", "Ожидания": "Waiting", "Ожидать": "Wait",
    "Совпадение": "Match", "Совпадения": "Match", "Совпадений": "Matches",
    "Объявление": "Declaration", "Объявления": "Declaration",
    "Определение": "Definition", "Определения": "Definition",
    "Видимость": "Visibility",
    "Доступность": "Availability",
    "Сущность": "Entity", "Сущности": "Entity",
    "Учет": "Accounting", "Учета": "Accounting",

    # ─── Miscellaneous ───
    "Период": "Period", "Периода": "Period",
    "Время": "Time", "Времени": "Time",
    "Дерево": "Tree", "Дерева": "Tree",
    "Диаграмма": "Chart", "Диаграммы": "Chart", "Диаграмм": "Charts",
    "Планировщик": "Scheduler", "Планировщика": "Scheduler",
    "Географическая": "Geographic", "Географической": "Geographic",
    "Графическая": "Graphic", "Графической": "Graphic",
    "Речь": "Speech", "Речи": "Speech", "Речью": "Speech",
    "Текст": "Text", "Текста": "Text", "Тексте": "Text", "Текстовый": "Text",
    "История": "History", "Истории": "History",
    "Работа": "Work", "Работы": "Work",
    "Серия": "Series", "Серии": "Series",
    "Прогноз": "Forecast", "Прогноза": "Forecast",
    "Слой": "Layer", "Слоя": "Layer",
    "Ганта": "Gantt",
    "Перетаскивание": "DragAndDrop", "Перетаскивания": "DragAndDrop",
    "Через": "Via",
    "Об": "About",
    "Связь": "Link", "Связи": "Link",
    "Место": "Place", "Места": "Places",
    "Вложение": "Attachment", "Вложения": "Attachment",
    "Асинх": "Async",
    "Фикс": "Fix",
    "Обсуждение": "Discussion", "Обсуждения": "Discussion",
    "Модель": "Model", "Модели": "Model",
    "Документация": "Documentation",
    "Разряд": "Digit", "Разрядов": "Digits",
    "Включающего": "Including", "Исключающего": "Excluding",
    "Посетить": "Visit",
    "Ганта": "Gantt",

    # ─── Code keywords translated ───
    "Если": "If", "Тогда": "Then", "Иначе": "Else",
    "Процедуры": "Procedures",
    "Препроцессор": "Preprocessor", "Препроцессора": "Preprocessor",

    # ─── Single letters (often abbreviations) ───
    "Д": "D", "Е": "E", "З": "Z", "Л": "L", "М": "M",
    "Н": "N", "П": "P", "Р": "R", "Т": "T", "У": "U",

    # ─── Фасет (XML Schema facets) ───
    "Фасет": "Facet", "Фасета": "Facet", "Фасетов": "Facets",
}


# ── Translation cache ─────────────────────────────────────────────────────

CACHE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'translation_cache.json')


def load_cache() -> dict:
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}


def save_cache(cache: dict):
    with open(CACHE_FILE, 'w', encoding='utf-8') as f:
        json.dump(cache, f, ensure_ascii=False, indent=2, sort_keys=True)


# ── Transliteration detection ──────────────────────────────────────────────

STRONG = [
    r'shch', r'(?<![a-z])kh(?=[aeiouy])', r'(?<![a-z])zh(?=[aeiouy])',
    r'yy\b', r'yy(?=[A-Z])', r'(?i)ovaniy', r'(?i)eniy[ae]', r'(?i)aniy[ae]',
]
MEDIUM = [
    r'(?i)znach', r'(?i)polzov', r'(?i)nastro', r'(?i)obnovl',
    r'(?i)sozda', r'(?i)udalen', r'(?i)izmenen', r'(?i)vypoln',
    r'(?i)zagruz', r'(?i)soobshch', r'(?i)tablits', r'(?i)spravochn',
    r'(?i)khranilishch', r'(?i)opisani', r'(?i)opoveshch', r'(?i)peremenn',
    r'(?i)metadann', r'(?i)rasshiren', r'(?i)konfigurats', r'(?i)ssylk[aiu]',
    r'(?i)svoystvo', r'(?i)podpisk', r'(?i)rekvizit', r'(?i)vychisly',
    r'(?i)formirova', r'(?i)otladk', r'(?i)vygruz', r'(?i)dvizhen',
    r'(?i)perechislen', r'(?i)otbor', r'(?i)regulyarn',
    r'(?i)dokument(?!s\b|ation|ed|ing)',
    r'(?i)registr(?!at|y\b|ed|ing)',
    r'(?i)obrabot', r'(?i)spiso[ck]', r'(?i)parametr(?!s\b|ic)',
    r'(?i)funkts', r'(?i)protsed', r'(?i)pereme',
    r'(?i)konstant', r'(?i)soedineniy', r'(?i)podklyuch',
    r'(?i)avtoregistrats', r'(?i)avtoobnov',
    r'(?i)vyrazhen', r'(?i)neopredeleno',
]
WEAK = [
    r'(?i)iya\b', r'(?i)iye\b', r'(?i)ovk[aiu]', r'(?i)osti\b', r'(?i)stvo\b',
    r'(?i)tekushch', r'(?i)dlya\b', r'(?i)novyy', r'(?i)staryy',
]


def translit_score(val: str) -> int:
    if not val or len(val) <= 2:
        return 0
    s = 0
    for p in STRONG:
        if re.search(p, val): s += 3
    for p in MEDIUM:
        if re.search(p, val): s += 2
    for p in WEAK:
        if re.search(p, val): s += 1
    return s


def is_transliteration(val: str) -> bool:
    return translit_score(val) >= 2


# ── CamelCase operations ─────────────────────────────────────────────────

def split_camelcase_ru(text: str) -> list[str]:
    if not text:
        return []
    return re.findall(r'[А-ЯЁ][а-яё]*|[A-Z][a-z]*|[a-z]+|[а-яё]+|\d+|[_]+', text)


# ── Translation engine ────────────────────────────────────────────────────

_translator = None
_api_calls = 0


def get_translator():
    global _translator
    if _translator is None:
        from deep_translator import GoogleTranslator
        _translator = GoogleTranslator(source='ru', target='en')
    return _translator


def translate_word_google(word: str, cache: dict) -> str | None:
    """Translate a single word via Google Translate with caching."""
    cache_key = f"g:{word}"
    if cache_key in cache:
        return cache[cache_key]

    global _api_calls
    try:
        result = get_translator().translate(word)
        _api_calls += 1
        if _api_calls % 100 == 0:
            print(f"  [API calls: {_api_calls}...]", file=sys.stderr)
            time.sleep(0.3)
        if result:
            clean = result.split()[0].strip('.,;:!?')
            cache[cache_key] = clean
            return clean
    except Exception as e:
        if _api_calls % 50 == 0:
            print(f"  [translate error: {e}]", file=sys.stderr)
        time.sleep(1)
    return None


def translate_word(word: str, cache: dict) -> str | None:
    """Translate a Russian word: 1C dict first, then Google Translate."""
    # 1. Direct 1C dictionary lookup
    if word in DICT_1C:
        return DICT_1C[word]

    # 2. Try imported WORDS dict
    try:
        from ru_en_words import WORDS
        if word in WORDS:
            return WORDS[word]
    except ImportError:
        pass

    # 3. Google Translate fallback
    return translate_word_google(word, cache)


def translate_camelcase(ru_text: str, cache: dict) -> str | None:
    """Translate Russian CamelCase to English CamelCase word-by-word."""
    words = split_camelcase_ru(ru_text)
    if not words:
        return None

    result = []
    for word in words:
        if re.match(r'^[A-Za-z0-9_]+$', word):
            result.append(word)
            continue

        if not re.search(r'[а-яА-ЯёЁ]', word):
            result.append(word)
            continue

        en = translate_word(word, cache)
        if en:
            result.append(en.capitalize())
        else:
            return None  # Can't translate

    translated = ''.join(result)

    # Verify it's not still a transliteration
    if is_transliteration(translated):
        return None

    return translated


# ── File processors ──────────────────────────────────────────────────────

def process_camelcase_dict(src_dir: str, cache: dict, fix: bool = False):
    dict_path = os.path.join(src_dir, 'common-camelcase_en.dict')
    stats = {'total': 0, 'translit': 0, 'fixed': 0, 'unfixable': 0}

    with open(dict_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    new_lines = []
    fixes = []

    for line in lines:
        stripped = line.rstrip('\n')
        if not stripped or stripped.startswith('#'):
            new_lines.append(line)
            continue
        if '=' not in stripped:
            new_lines.append(line)
            continue

        key, _, val = stripped.partition('=')
        stats['total'] += 1

        if not is_transliteration(val):
            new_lines.append(line)
            continue

        stats['translit'] += 1
        translated = translate_camelcase(key, cache)

        if translated and translated != val:
            stats['fixed'] += 1
            fixes.append((key, val, translated))
            new_lines.append(f'{key}={translated}\n' if fix else line)
        else:
            stats['unfixable'] += 1
            new_lines.append(line)

    if fix:
        with open(dict_path, 'w', encoding='utf-8') as f:
            f.writelines(new_lines)

    return stats, fixes


def process_trans_files(src_dir: str, cache: dict, fix: bool = False):
    stats = {'total_files': 0, 'total_entries': 0, 'translit': 0, 'fixed': 0, 'unfixable': 0}
    fixes = []

    for dirpath, _, filenames in os.walk(src_dir):
        for fname in filenames:
            if not fname.endswith('_en.trans'):
                continue

            filepath = os.path.join(dirpath, fname)
            rel_path = os.path.relpath(filepath, src_dir)
            stats['total_files'] += 1

            with open(filepath, 'r', encoding='utf-8') as f:
                lines = f.readlines()

            new_lines = []
            file_changed = False

            for line in lines:
                stripped = line.rstrip('\n')
                if not stripped or stripped.startswith('#'):
                    new_lines.append(line)
                    continue
                if '=' not in stripped:
                    new_lines.append(line)
                    continue

                trans_key, _, val = stripped.partition('=')
                stats['total_entries'] += 1

                if not val or not is_transliteration(val):
                    new_lines.append(line)
                    continue

                stats['translit'] += 1

                # Extract Russian name from key path
                parts = trans_key.split('.')
                ru_name = None
                for p in parts:
                    if re.search(r'[а-яА-ЯёЁ]', p):
                        ru_name = p
                        break

                translated = translate_camelcase(ru_name, cache) if ru_name else None

                if translated and translated != val:
                    stats['fixed'] += 1
                    fixes.append((rel_path, trans_key, val, translated))
                    if fix:
                        new_lines.append(f'{trans_key}={translated}\n')
                        file_changed = True
                    else:
                        new_lines.append(line)
                else:
                    stats['unfixable'] += 1
                    new_lines.append(line)

            if fix and file_changed:
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.writelines(new_lines)

    return stats, fixes


# ── Main ──────────────────────────────────────────────────────────────────

def main():
    root_dir = os.path.dirname(os.path.abspath(__file__))
    src_dir = os.path.join(root_dir, 'src')

    args = set(sys.argv[1:])
    if not args:
        args = {'--analyze'}

    do_analyze = '--analyze' in args
    do_fix_dict = '--fix-dict' in args or '--fix-all' in args
    do_fix_trans = '--fix-trans' in args or '--fix-all' in args
    do_stats = '--stats' in args

    cache = load_cache()
    print(f"Translation cache: {len(cache)} entries")
    print(f"1C dictionary: {len(DICT_1C)} entries")

    try:
        # CamelCase dict
        print("\n" + "=" * 80)
        print("COMMON-CAMELCASE_EN.DICT")
        print("=" * 80)
        stats, fixes = process_camelcase_dict(src_dir, cache, fix=do_fix_dict)
        print(f"Total: {stats['total']}, Translit: {stats['translit']}, "
              f"Can fix: {stats['fixed']}, Unfixable: {stats['unfixable']}")
        if do_fix_dict:
            print(f">>> APPLIED {stats['fixed']} fixes")
        if (do_analyze or do_stats) and fixes:
            print(f"\nSample fixes ({min(40, len(fixes))} of {len(fixes)}):")
            for key, old, new in fixes[:40]:
                print(f"  {key}: {old} -> {new}")

        # Trans files
        print("\n" + "=" * 80)
        print("_EN.TRANS FILES")
        print("=" * 80)
        stats2, fixes2 = process_trans_files(src_dir, cache, fix=do_fix_trans)
        print(f"Files: {stats2['total_files']}, Entries: {stats2['total_entries']}, "
              f"Translit: {stats2['translit']}, Can fix: {stats2['fixed']}, "
              f"Unfixable: {stats2['unfixable']}")
        if do_fix_trans:
            print(f">>> APPLIED {stats2['fixed']} fixes")
        if (do_analyze or do_stats) and fixes2:
            print(f"\nSample fixes ({min(30, len(fixes2))} of {len(fixes2)}):")
            for filepath, key, old, new in fixes2[:30]:
                print(f"  {key}: {old} -> {new}")

    finally:
        save_cache(cache)
        print(f"\nCache saved: {len(cache)} entries, API calls: {_api_calls}")


if __name__ == '__main__':
    main()
