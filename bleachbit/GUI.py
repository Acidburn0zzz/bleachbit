# vim: ts=4:sw=4:expandtab

## BleachBit
## Copyright (C) 2008 Andrew Ziem
## http://bleachbit.sourceforge.net
##
## This program is free software: you can redistribute it and/or modify
## it under the terms of the GNU General Public License as published by
## the Free Software Foundation, either version 3 of the License, or
## (at your option) any later version.
## 
## This program is distributed in the hope that it will be useful,
## but WITHOUT ANY WARRANTY; without even the implied warranty of
## MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
## GNU General Public License for more details.
## 
## You should have received a copy of the GNU General Public License
## along with this program.  If not, see <http://www.gnu.org/licenses/>.




import gettext
gettext.install("bleachbit")
import pygtk
pygtk.require('2.0')
import gtk
import gobject
import sys
import threading

import FileUtilities
import CleanerBackend
import Update
from Options import options
from globals import *



def on_url(about, link):
    """Event to open a URL"""
    try:
        import gnomevfs
        gnomevfs.url_show(link)
        return
    except:
        import webbrowser
        webbrowser.open(link)

gtk.about_dialog_set_url_hook(on_url)


def threaded(f):
    """Decoration to create a threaded function"""
    def wrapper(*args):
        t = threading.Thread(target=f, args=args)
        t.start()
    return wrapper


def delete_confirmation_dialog(parent):
    """Return boolean whether OK to delete files."""
    dialog = gtk.Dialog(title = _("Delete confirmation"), parent = parent, flags = gtk.DIALOG_MODAL | gtk.DIALOG_DESTROY_WITH_PARENT)
    dialog.set_default_size(300, -1)

    hbox = gtk.HBox(homogeneous=False, spacing=10)
    icon = gtk.Image()
    icon.set_from_stock(gtk.STOCK_DIALOG_WARNING, gtk.ICON_SIZE_DIALOG)
    hbox.pack_start(icon, False)
    question = gtk.Label(_("Are you sure you want to delete files according to the selected operations?  The actual files that will be deleted may have changed since you ran the preview.  Files cannot be undeleted."))
    question.set_line_wrap(True)
    hbox.pack_start(question, False)    
    dialog.vbox.pack_start(hbox, False)
    dialog.vbox.set_spacing(10)

    dialog.add_button(gtk.STOCK_CANCEL, False)
    dialog.add_button(gtk.STOCK_DELETE, True)
    dialog.set_default_response(gtk.RESPONSE_CANCEL)

    dialog.show_all()
    r = dialog.run()
    dialog.destroy()
    return r


class TreeInfoModel:
    """Model holds information to be displayed in the tree view"""
    def __init__(self):
        self.tree_store = gtk.TreeStore(gobject.TYPE_STRING, gobject.TYPE_BOOLEAN, gobject.TYPE_PYOBJECT)
        for key in sorted(CleanerBackend.backends):
            c_name = CleanerBackend.backends[key].get_name()
            c_id = CleanerBackend.backends[key].get_id()
            parent = self.tree_store.append(None, (c_name, None, c_id))
            for (o_id, o_name, o_value) in CleanerBackend.backends[key].get_options():
                self.tree_store.append(parent, (o_name, None, o_id))                                
        if None == self.tree_store:
            raise Exception("cannot create tree store")
        return

    def get_model(self):
        return self.tree_store


class TreeDisplayModel:
    """Displays the info model in a view"""

    def make_view(self, model):
        self.view = gtk.TreeView(model)

        # first column
        self.renderer0 = gtk.CellRendererText()
        self.column0 = gtk.TreeViewColumn("Name", self.renderer0, text=0)
        self.view.append_column(self.column0)

        # second column
        self.renderer1 = gtk.CellRendererToggle()
        self.renderer1.set_property('activatable', True)
        self.renderer1.connect('toggled', self.col1_toggled_cb, model)
        self.column1 = gtk.TreeViewColumn("Active", self.renderer1)
        self.column1.add_attribute(self.renderer1, "active", 1)
        self.view.append_column(self.column1)

        # finish
        self.view.expand_all()
        return self.view

    def col1_toggled_cb(self, cell, path, model):
        """When toggles the checkbox"""
        model[path][1] = not model[path][1]
        i = model.get_iter(path)
        # if toggled on, enable the parent
        parent = model.iter_parent(i)
        if None != parent and model[path][1]:
            model[parent][1] = True
        # if all siblings toggled off, disable the parent
        if parent and not model[path][1]:
            sibling = model.iter_nth_child(parent, 0)
            any_true = False
            while sibling:
                print "debug: col1_toggled_cb: %s = %s" % (model[sibling][0], model[sibling][1])
                #mode[sibling][1] = False
                if model[sibling][1]:
                    any_true = True
                sibling = model.iter_next(sibling)
            if not any_true:
                model[parent][1] = False                
        # if toggled and has children, do the same for each child
        child = model.iter_children(i)
        while child:
            model[child][1] = model[path][1]            
            child = model.iter_next(child)
        return



class GUI:

    ui = \
        '''<ui>
    <menubar name="MenuBar">
      <menu action="File">
        <menuitem action="Quit"/>
      </menu>
      <menu action="Help">      
        <menuitem action="About"/>
      </menu>
    </menubar>
    </ui>'''


    def on_selection_changed(self, selection):
        """When the tree view selection changed"""
        model = self.view.get_model()
        paths = selection.get_selected_rows()[1][0]
        row = paths[0]
        #print "debug: on_selection_changed: paths = '%s', row='%s', model[paths][0]  = '%s'" % (paths,row, model[paths][0])
        name = model[row][0]
        id = model[row][2]
        self.progressbar.hide()
        description = CleanerBackend.backends[id].get_description()
        #print "debug: on_selection_changed: row='%s', name='%s', desc='%s'," % ( row, name ,description)
        output = "Operation name: " + name + "\n"
        output += "Description: " + description 
        self.textbuffer.set_text(output)


    def get_selected_operations(self):
        """Return a list of the IDs of the selected operations in the tree view"""
        r = []
        model = self.tree_store.get_model()
        iter = model.get_iter_root()
        while iter:
            #print "debug: get_selected_operations: iter id = '%s', value='%s'" % (model[iter][2], model[iter][1])
            if True == model[iter][1]:
                r.append(model[iter][2])
            iter = model.iter_next(iter)
        return r

    def get_operation_options(self, operation):
        """For the given operation ID, return a list of the selected option IDs."""
        r = []
        model = self.tree_store.get_model()
        iter = model.get_iter_root()
        while iter:
            #print "debug: get_operation_options: iter id = '%s', value='%s'" % (model[iter][2], model[iter][1])
            if operation == model[iter][2]:
                iterc = model.iter_children(iter)            
                if None == iterc:
                    #print "debug: no children"
                    return None
                while iterc:
                    tuple = (model[iterc][2], model[iterc][1])
                    #print "debug: get_operation_options: tuple = '%s'" % (tuple,)
                    r.append(tuple)
                    iterc = model.iter_next(iterc)
                return r
            iter = model.iter_next(iter)
        return None


    def set_sensitive(self, true):
        """Disable commands while an operation is running"""
        print "debug: set_sensitive '%s'" % (true)
        self.actiongroup.set_sensitive(true)
        self.toolbar.set_sensitive(true)


    def run_operations(self, widget):
        """Event when the 'delete' toolbar button is clicked."""
        # fixme: should present this dialog after finding operations
        if not True == delete_confirmation_dialog(self.window):
            return
        self.preview_or_run_operations(True)


    def preview_operations(self, widget):
        """Event when the 'preview operations' toolbar button is clicked."""
        self.preview_or_run_operations(False)

    @threaded
    def preview_or_run_operations(self, really_delete):
        operations = self.get_selected_operations()
        if 0 == len(operations):
            gtk.gdk.threads_enter()
            dialog = gtk.MessageDialog(self.window, gtk.DIALOG_MODAL | gtk.DIALOG_DESTROY_WITH_PARENT, gtk.MESSAGE_WARNING, gtk.BUTTONS_OK, _("You must select an operation"))
            dialog.run()
            dialog.destroy()
            gtk.gdk.threads_leave()
            return
        gtk.gdk.threads_enter()
        self.set_sensitive(False)
        self.textbuffer.set_text("")
        iter = self.textbuffer.get_iter_at_offset(0)
        self.progressbar.show()
        gtk.gdk.threads_leave()
        total_bytes = 0
        count = 0
        for operation in operations:
            gtk.gdk.threads_enter()
            self.progressbar.set_fraction(1.0*count / len(operations))
            if really_delete:
                self.progressbar.set_text(_("Please wait.  Scanning and deleting: ") + operation)
            else:
                self.progressbar.set_text(_("Please wait.  Scanning: ") + operation)
            gtk.gdk.threads_leave()
            options = self.get_operation_options(operation)
            print "debug: options = '%s'" % (options,)
            if options:
                for (option,value) in options:
                    CleanerBackend.backends[operation].set_option(option,value)
            for file in CleanerBackend.backends[operation].list_files():
                #print "preview_operations, file='%s'" % (file,)
                try:
                    bytes = FileUtilities.size_of_file(file)
                except:
                    print "debug: error getting size of '%s'" % (file,)
                    pass
                else:
                    try:
                        if really_delete:
                            FileUtilities.delete_file_directory(file)
                    except:
                        line = str(sys.exc_info()[1]) + " " + file + "\n"
                    else:
                        total_bytes += bytes
                        line = FileUtilities.bytes_to_human(bytes) + " " + file+"\n"
                    gtk.gdk.threads_enter()
                    self.textbuffer.insert(iter, line)
                    gtk.gdk.threads_leave()
            count += 1

        gtk.gdk.threads_enter()
        self.progressbar.set_text("")
        self.progressbar.set_fraction(1)
        self.progressbar.set_text(_("Done."))
        self.textbuffer.insert(iter, "\nTotal size:" + FileUtilities.bytes_to_human(total_bytes))
        self.set_sensitive(True)
        gtk.gdk.threads_leave()


    def about(self, x):
        """Create and show the about dialog"""
        a = gtk.AboutDialog()
        a.set_comments(_("Program to clean unnecessary files"))
        a.set_copyright("Copyright (c) 2008 by Andrew Ziem")
        try:
            a.set_license(open(license_filename).read())
        except:
            a.set_license(_("GNU General Public License version 3 or later.\nSee http://www.gnu.org/licenses/gpl-3.0.txt"))
        a.set_name(APP_NAME)
        a.set_website("http://bleachbit.sourceforge.net")
        a.run()
        a.hide()


    def first_start(self):
        """Setup application for first start"""

        if not online_update_notification_enabled:
            return

        dialog = gtk.Dialog(title = _("Welcome"), parent = self.window, flags = gtk.DIALOG_MODAL | gtk.DIALOG_DESTROY_WITH_PARENT)
        dialog.set_default_size(300, -1)

        hbox = gtk.HBox(homogeneous = False, spacing = 10)
        icon = gtk.Image()
        icon.set_from_stock(gtk.STOCK_DIALOG_QUESTION, gtk.ICON_SIZE_DIALOG)
        hbox.pack_start(icon, False)
        question = gtk.Label(_("Should BleachBit periodically check for software updates via the Internet?"))
        question.set_line_wrap(True)
        hbox.pack_start(question, False)
        dialog.vbox.pack_start(hbox, False)
        dialog.vbox.set_spacing(10)

        dialog.add_button(gtk.STOCK_YES, 1)
        dialog.add_button(gtk.STOCK_NO, 0)

        dialog.show_all()
        r = dialog.run()
        dialog.destroy()

        options.set("check_online_updates", r == 1)
        options.set("first_start", False)
        return



    def create_operations_box(self):
        """Create and return the operations box (which holds a tree view)"""
        scrolled_window = gtk.ScrolledWindow()
        scrolled_window.set_policy(gtk.POLICY_NEVER, gtk.POLICY_AUTOMATIC)
        self.tree_store = TreeInfoModel()
        Display = TreeDisplayModel()
        mdl = self.tree_store.get_model()
        self.view = Display.make_view(mdl)
        self.view.get_selection().connect("changed", self.on_selection_changed)
        scrolled_window.add_with_viewport(self.view)
        return scrolled_window


    def create_menubar(self):
        """Create the menu bar (file, help)"""
        # Create a UIManager instance
        uimanager = gtk.UIManager()

        # Add the accelerator group to the toplevel window
        accelgroup = uimanager.get_accel_group()
        self.window.add_accel_group(accelgroup)

        # Create an ActionGroup
        actiongroup = gtk.ActionGroup('UIManagerExample')
        self.actiongroup = actiongroup

        # Create actions
        actiongroup.add_actions([('Quit', gtk.STOCK_QUIT, '_Quit', None, 'Quit the Program', self.quit_cb), 
                                ('File', None, '_File'), 
                                ('About', gtk.STOCK_ABOUT, '_About', None, 'Show about', self.about), 
                                ('Help', None, '_Help')])
        actiongroup.get_action('Quit').set_property('short-label', '_Quit')

        # Add the actiongroup to the uimanager
        uimanager.insert_action_group(actiongroup, 0)

        # Add a UI description
        uimanager.add_ui_from_string(self.ui)

        # Create a MenuBar
        menubar = uimanager.get_widget('/MenuBar')
        return menubar

    def create_toolbar(self):
        """Create the toolbar"""
        toolbar = gtk.Toolbar()
        toolbar.set_orientation(gtk.ORIENTATION_HORIZONTAL)
        #toolbar.set_style(gtk.TOOLBAR_TEXT)
        toolbar.set_style(gtk.TOOLBAR_BOTH)
        toolbar.set_border_width(5)

        icon = gtk.Image()
        icon.set_from_stock(gtk.STOCK_DELETE, gtk.ICON_SIZE_LARGE_TOOLBAR)
        run_button = gtk.ToolButton(icon_widget = icon, label = _("Delete"))
        run_button.show()
        run_button.connect("clicked", self.run_operations)
        toolbar.insert(run_button, -1)

        preview_icon = gtk.Image()
        preview_icon.set_from_stock(gtk.STOCK_FIND, gtk.ICON_SIZE_LARGE_TOOLBAR)
        preview_button = gtk.ToolButton(icon_widget = preview_icon, label = _("Preview"))
        preview_button.show()

        preview_button.connect("clicked", self.preview_operations)
        toolbar.insert(preview_button, -1)
        return toolbar

    def create_window(self):
        """Create the main application window"""
        self.window = gtk.Window()
        self.window.connect('destroy', lambda w: gtk.main_quit())

        self.window.resize(800, 600)
        self.window.set_title(APP_NAME)
        vbox = gtk.VBox()
        self.window.add(vbox)

        # add menubar
        vbox.pack_start(self.create_menubar(), False)

        # add toolbar
        self.toolbar = self.create_toolbar()
        vbox.pack_start(self.toolbar, False)

        # split main window
        hbox = gtk.HBox(homogeneous=False, spacing=10)
        vbox.pack_start(hbox, True)
        hbox.show()

        # add operations to left
        operations = self.create_operations_box()
        hbox.pack_start(operations, False)
        operations.show()

        # create the right side of the window
        right_box = gtk.VBox()
        self.progressbar = gtk.ProgressBar()
        right_box.pack_start(self.progressbar, False)

        # add output display on right
        self.textbuffer = gtk.TextBuffer()
        sw = gtk.ScrolledWindow()
        sw.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        textview = gtk.TextView(self.textbuffer)
        textview.set_editable(False)
        sw.add(textview)
        sw.show()
        right_box.add(sw)
        hbox.add(right_box)
        textview.show()

        # done
        self.window.show_all()
        self.progressbar.hide()
        return

    def enable_online_update(self, url):
        """Create a button to launch browser to initiate software update"""
        icon = gtk.Image()
        icon.set_from_stock(gtk.STOCK_NETWORK, gtk.ICON_SIZE_LARGE_TOOLBAR)
        update_button = gtk.ToolButton(icon_widget = icon, label = _("Update BleachBit"))
        update_button.show_all()
        update_button.connect("clicked", on_url, url)
        self.toolbar.insert(update_button, -1)
        try:
            import pynotify
        except:
            print "debug: pynotify not available"
        else:
            if pynotify.init(APP_NAME):
                n = pynotify.Notification(_("BleachBit update is available"), _("Click 'Update BleachBit' for more information"))
                # this doesn't align the notification properly
                #n.attach_to_widget(update_button)
                n.attach_to_widget(self.toolbar)
                n.show()

    @threaded
    def check_online_updates(self):
        """Check for software updates in background"""
        u = Update.Update()
        if u.is_update_available():
            gobject.idle_add(self.enable_online_update, u.get_update_url())

    def __init__(self):
        self.create_window()
        gtk.gdk.threads_init()
        if options.get("first_start"):
            self.first_start()
        if online_update_notification_enabled and options.get("check_online_updates"):
            self.check_online_updates()

    def quit_cb(self, b):
        """Quit callback"""
        print 'Quitting program'
        gtk.main_quit()

if __name__ == '__main__':
    gui = GUI()
    gtk.main()

